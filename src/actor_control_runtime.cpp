#include "actor_control_runtime.h"

#include <algorithm>
#include <chrono>
#include <cwchar>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <map>
#include <sstream>
#include <stdexcept>
#include <utility>
#include <vector>

#ifdef _WIN32
#include "platform_win.h"
#endif

#include "actor_control.h"
#include "actor_control_bridge.h"
#include "actor_control_files.h"
#include "actor_control_protocol.h"
#include "actor_control_protocol_generated.h"
#include "flexbuffer_json.h"
#include "json_loader.h"
#include "path_info.h"

namespace cata::actor_control
{
namespace
{
constexpr std::size_t maximum_profile_bytes = 1024 * 1024;
std::filesystem::path bundle_root()
{
    return std::filesystem::absolute( PATH_INFO::base_path().get_unrelative_path() /
                                      "companion-runtime" ).lexically_normal();
}

std::string read_text( const std::filesystem::path &path )
{
    if( std::filesystem::file_size( path ) > maximum_profile_bytes ) {
        throw std::runtime_error( "runtime_profile_oversized" );
    }
    std::ifstream input( path, std::ios::binary );
    if( !input ) {
        throw std::runtime_error( "runtime_profile_unavailable" );
    }
    const std::string text( ( std::istreambuf_iterator<char>( input ) ),
                            std::istreambuf_iterator<char>() );
    if( text.size() > maximum_profile_bytes ) {
        throw std::runtime_error( "runtime_profile_oversized" );
    }
    return text;
}

JsonObject object( const std::string &text )
{
    JsonObject value = json_loader::from_string( text ).get_object();
    value.allow_omitted_members();
    return value;
}

std::string merged( const JsonObject &original, const std::map<std::string, std::string> &changes )
{
    std::map<std::string, std::string> members;
    for( const JsonMember &entry : original ) {
        members[entry.name()] = stringify( entry );
    }
    for( const auto &entry : changes ) {
        members[entry.first] = entry.second;
    }
    std::string result = "{";
    for( const auto &entry : members ) {
        result += ( result.size() == 1 ? "" : "," ) + quote( entry.first ) + ":" + entry.second;
    }
    return result + "}";
}

std::string array( const std::vector<std::string> &values )
{
    std::string result = "[";
    for( const std::string &value : values ) {
        result += ( result.size() == 1 ? "" : "," ) + quote( value );
    }
    return result + "]";
}

std::vector<std::string> strings( const JsonObject &parent, const char *key )
{
    std::vector<std::string> result;
    if( parent.has_array( key ) ) {
        for( const std::string value : parent.get_array( key ) ) {
            result.push_back( value );
        }
    }
    return result;
}

bool write_private( const std::filesystem::path &path, const std::string &text )
{
    const std::filesystem::path temporary = path.parent_path() /
                                            ( path.filename().u8string() + ".new-" + new_identity() );
    const int fd = files::open( temporary, files::access::create_new );
    if( fd < 0 ) {
        return false;
    }
    std::size_t written = 0;
    while( written < text.size() ) {
        const std::ptrdiff_t amount = files::write( fd, text.data() + written, text.size() - written );
        if( amount <= 0 ) {
            break;
        }
        written += amount;
    }
    const bool durable = written == text.size() && files::sync( fd ) == 0;
    files::close( fd );
    if( !durable || files::replace( temporary, path ) != 0 ) {
        files::remove( temporary );
        return false;
    }
    return files::sync_directory( path.parent_path() ) == 0;
}

std::filesystem::path background_path( const runtime_preferences &value )
{
    const JsonObject config = object( value.configuration );
    const JsonObject paths = config.get_object( "paths" );
    paths.allow_omitted_members();
    const std::filesystem::path path = std::filesystem::u8path( paths.get_string( "background" ) );
    return path.is_absolute() ? path : runtime_profile_directory( value.profile_id ) / path;
}

#ifdef _WIN32
struct owned_process {
    HANDLE process = nullptr;
    HANDLE job = nullptr;
    std::chrono::steady_clock::time_point stop_deadline {};
    ~owned_process() {
        // Child cleanup is scoped to the process this game created. Closing
        // the job cannot terminate the game or an unrelated Python process.
        if( job ) {
            CloseHandle( job );
        }
        if( process ) {
            CloseHandle( process );
        }
    }
};

owned_process &child()
{
    static owned_process value;
    return value;
}

std::wstring wide( const std::string &text )
{
    if( text.empty() ) {
        return {};
    }
    const int size = MultiByteToWideChar( CP_UTF8, MB_ERR_INVALID_CHARS, text.data(),
                                        static_cast<int>( text.size() ), nullptr, 0 );
    if( size <= 0 ) {
        throw std::runtime_error( "runtime_invalid_text" );
    }
    std::wstring result( size, L'\0' );
    MultiByteToWideChar( CP_UTF8, MB_ERR_INVALID_CHARS, text.data(),
                         static_cast<int>( text.size() ), result.data(), size );
    return result;
}

std::wstring argument( const std::wstring &value )
{
    std::wstring result = L"\"";
    std::size_t slashes = 0;
    for( const wchar_t character : value ) {
        if( character == L'\\' ) {
            ++slashes;
        } else {
            result.append( slashes * ( character == L'\"' ? 2 : 1 ), L'\\' );
            slashes = 0;
            if( character == L'\"' ) {
                result += L'\\';
            }
            result += character;
        }
    }
    result.append( slashes * 2, L'\\' );
    return result + L'\"';
}
#endif
} // namespace

std::filesystem::path runtime_profile_directory( const std::string &profile_id )
{
    if( profile_id.empty() || profile_id.size() > 128 ) {
        throw std::runtime_error( "runtime_invalid_profile" );
    }
    constexpr char digits[] = "0123456789abcdef";
    std::string directory;
    for( const unsigned char character : profile_id ) {
        directory += digits[character >> 4];
        directory += digits[character & 15];
    }
    return std::filesystem::absolute( PATH_INFO::user_dir_path().get_unrelative_path() /
                                      "ai-companion" / "profiles" / directory ).lexically_normal();
}

bool read_runtime_preferences( const std::string &profile_id, const int actor_id,
                               runtime_preferences &result, std::string &error )
{
    error.clear();
    try {
        result = runtime_preferences();
        result.profile_id = profile_id;
        result.actor_id = actor_id;
        const std::filesystem::path profile = runtime_profile_directory( profile_id );
        const bool existing = std::filesystem::exists( profile / "config.json" );
        result.configuration = read_text( existing ? profile / "config.json" :
                                          bundle_root() / "config.default.json" );
        const JsonObject config = object( result.configuration );
        const JsonObject llm = config.get_object( "llm" );
        llm.allow_omitted_members();
        if( config.has_member( "api_key" ) || llm.has_member( "api_key" ) ) {
            throw std::runtime_error( "runtime_profile_invalid" );
        }
        result.endpoint = llm.get_string( "base_url", "" );
        result.model = llm.get_string( "model", "" );
        if( config.has_object( "duties" ) ) {
            const JsonObject duties = config.get_object( "duties" );
            duties.allow_omitted_members();
            result.duties = strings( duties, "allowed_tasks" );
            result.item_types = strings( duties, "item_types" );
            result.recipes = strings( duties, "recipes" );
            result.max_distance = duties.get_int( "max_distance", 12 );
        }
        const std::filesystem::path source = existing ? background_path( result ) :
                                             bundle_root() / "background.default.md";
        result.background = read_text( source );
        return true;
    } catch( const std::exception & ) {
        error = "runtime_profile_unavailable";
        return false;
    }
}

bool save_runtime_preferences( const runtime_preferences &value, std::string &error )
{
    error.clear();
    try {
        const bool apply_to_binding = has_binding();
        if( apply_to_binding ) {
            const JsonObject current = object( status() );
            if( current.get_string( "profile_id" ) != value.profile_id ||
                current.get_int( "actor_id" ) != value.actor_id ) {
                error = "fixed_binding_conflict";
                return false;
            }
        }
        if( value.actor_id < 0 || value.max_distance < 1 || value.max_distance > 60 ||
            value.background.size() > maximum_profile_bytes ||
            value.endpoint.size() > 4096 || value.model.size() > 256 ) {
            throw std::runtime_error( "runtime_profile_invalid" );
        }
        for( const std::string &duty : value.duties ) {
            if( duty != "follow" && duty != "guard" && duty != "move" && duty != "gather" &&
                duty != "craft" ) {
                throw std::runtime_error( "runtime_profile_invalid" );
            }
        }
        for( const auto *list : { &value.item_types, &value.recipes } ) {
            if( list->size() > 128 || std::any_of( list->begin(), list->end(), []( const std::string & id ) {
            return id.empty() || id.size() > 128 || id.find( '\0' ) != std::string::npos;
            } ) ) {
                throw std::runtime_error( "runtime_profile_invalid" );
            }
        }
        const JsonObject config = object( value.configuration );
        const JsonObject llm = config.get_object( "llm" );
        llm.allow_omitted_members();
        if( config.has_member( "api_key" ) || llm.has_member( "api_key" ) ) {
            throw std::runtime_error( "runtime_profile_invalid" );
        }
        const std::string llm_wire = merged( llm, {
            { "base_url", quote( value.endpoint ) }, { "model", quote( value.model ) },
            { "api_key_env", quote( "CPH_LLM_API_KEY" ) }
        } );
        const std::string duties = "{\"allowed_tasks\":" + array( value.duties ) +
                                   ",\"max_distance\":" + std::to_string( value.max_distance ) +
                                   ",\"item_types\":" + array( value.item_types ) + ",\"recipes\":" + array( value.recipes ) + "}";
        const std::string encoded = merged( config, {
            { "profile_id", quote( value.profile_id ) }, { "actor_id", std::to_string( value.actor_id ) },
            { "llm", llm_wire }, { "duties", duties }
        } );
        const std::filesystem::path directory = runtime_profile_directory( value.profile_id );
        const std::filesystem::path root = directory.parent_path().parent_path();
        for( const std::filesystem::path &path : { root, root / "profiles", directory } ) {
            if( files::create_private_directory( path ) != 0 ) {
                throw std::runtime_error( "runtime_profile_write_failed" );
            }
        }
        if( !write_private( background_path( value ), value.background ) ||
            !write_private( directory / "config.json", encoded + "\n" ) ) {
            throw std::runtime_error( "runtime_profile_write_failed" );
        }
        // File publication succeeds before native permissions change. These
        // validated values apply even when the model worker is disconnected.
        if( apply_to_binding && !configure_duties( value.profile_id, value.actor_id,
                object( duties ), error ) ) {
            return false;
        }
        return true;
    } catch( const std::exception & ) {
        error = "runtime_profile_write_failed";
        return false;
    }
}

bool bundled_runtime_available()
{
    try {
        const JsonObject manifest = object( read_text( bundle_root() / "manifest.json" ) );
        return manifest.get_int( "schema_version" ) == 1 &&
               manifest.get_string( "package_version" ) == "0.1.2.dev0" &&
               manifest.get_string( "protocol_digest" ) == protocol_digest &&
               std::filesystem::is_regular_file( bundle_root() / "python" / "python.exe" );
    } catch( const std::exception & ) {
        return false;
    }
}

bool managed_runtime_running()
{
#ifdef _WIN32
    owned_process &owned = child();
    if( owned.process && WaitForSingleObject( owned.process, 0 ) == WAIT_TIMEOUT ) {
        const JsonObject current = object( status() );
        if( current.get_string( "detach_state", "" ) != "detached" ) {
            owned.stop_deadline = {};
            return true;
        }
        const auto now = std::chrono::steady_clock::now();
        if( owned.stop_deadline == std::chrono::steady_clock::time_point() ) {
            owned.stop_deadline = now + std::chrono::seconds( 5 );
        }
        if( now < owned.stop_deadline ) {
            return true;
        }
        // Native work is already safely detached. Give the coordinator time
        // to exit normally, then retire only the game-owned child job.
        CloseHandle( owned.job );
        owned.job = nullptr;
        WaitForSingleObject( owned.process, 100 );
    }
    if( owned.process ) {
        CloseHandle( owned.process );
        owned.process = nullptr;
    }
    if( owned.job ) {
        CloseHandle( owned.job );
        owned.job = nullptr;
    }
#endif
    return false;
}

bool start_managed_runtime( const std::string &profile_id, const std::string &api_key,
                            std::string &error )
{
    error.clear();
#ifdef _WIN32
    if( managed_runtime_running() ) {
        error = "runtime_already_running";
        return false;
    }
    if( !bundled_runtime_available() || api_key.empty() || api_key.size() > 8192 ||
        api_key.find( '\0' ) != std::string::npos ) {
        error = "runtime_bundle_or_credential_missing";
        return false;
    }
    try {
        const JsonObject current = object( status() );
        const std::string descriptor = current.get_string( "descriptor_path", "" );
        if( !has_binding() || descriptor.empty() || current.get_string( "profile_id" ) != profile_id ) {
            error = "runtime_session_unavailable";
            return false;
        }
        const std::filesystem::path python = bundle_root() / "python" / "python.exe";
        std::wstring command = argument( python.wstring() ) +
                               L" -I -m cph_ai_companion.cli run --profile " +
                               argument( runtime_profile_directory( profile_id ).wstring() ) +
                               L" --session " + argument( wide( descriptor ) );
        std::vector<wchar_t> environment;
        std::vector<std::wstring> entries;
        wchar_t *const inherited = GetEnvironmentStringsW();
        if( !inherited ) {
            throw std::runtime_error( "runtime_start_failed" );
        }
        for( const wchar_t *entry = inherited; *entry; entry += wcslen( entry ) + 1 ) {
            // Drop inherited provider credentials as well as Python overrides.
            const std::wstring value( entry );
            const std::wstring name = value.substr( 0, value.find( L'=' ) );
            if( _wcsicmp( name.c_str(), L"CPH_LLM_API_KEY" ) != 0 &&
                _wcsicmp( name.c_str(), L"OPENAI_API_KEY" ) != 0 &&
                _wcsicmp( name.c_str(), L"PYTHONPATH" ) != 0 &&
                _wcsicmp( name.c_str(), L"PYTHONHOME" ) != 0 ) {
                entries.push_back( value );
            }
        }
        FreeEnvironmentStringsW( inherited );
        entries.push_back( L"CPH_LLM_API_KEY=" + wide( api_key ) );
        std::sort( entries.begin(), entries.end(), []( const std::wstring & left, const std::wstring & right ) {
            return _wcsicmp( left.c_str(), right.c_str() ) < 0;
        } );
        for( std::wstring &entry : entries ) {
            environment.insert( environment.end(), entry.begin(), entry.end() );
            environment.push_back( L'\0' );
            SecureZeroMemory( entry.data(), entry.size() * sizeof( wchar_t ) );
        }
        environment.push_back( L'\0' );
        HANDLE job = CreateJobObjectW( nullptr, nullptr );
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits {};
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if( !job || !SetInformationJobObject( job, JobObjectExtendedLimitInformation, &limits, sizeof( limits ) ) ) {
            if( job ) {
                CloseHandle( job );
            }
            throw std::runtime_error( "runtime_start_failed" );
        }
        STARTUPINFOW startup {};
        startup.cb = sizeof( startup );
        PROCESS_INFORMATION process {};
        const bool created = CreateProcessW( python.c_str(), command.data(), nullptr, nullptr, FALSE,
                                            CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT | CREATE_SUSPENDED,
                                            environment.data(), bundle_root().c_str(), &startup, &process );
        SecureZeroMemory( environment.data(), environment.size() * sizeof( wchar_t ) );
        if( !created ) {
            CloseHandle( job );
            throw std::runtime_error( "runtime_start_failed" );
        }
        if( !AssignProcessToJobObject( job, process.hProcess ) ) {
            TerminateProcess( process.hProcess, 1 );
            CloseHandle( process.hThread );
            CloseHandle( process.hProcess );
            CloseHandle( job );
            throw std::runtime_error( "runtime_start_failed" );
        }
        child().job = job;
        child().process = process.hProcess;
        if( ResumeThread( process.hThread ) == static_cast<DWORD>( -1 ) ) {
            CloseHandle( process.hThread );
            CloseHandle( child().job );
            child().job = nullptr;
            CloseHandle( child().process );
            child().process = nullptr;
            throw std::runtime_error( "runtime_start_failed" );
        }
        CloseHandle( process.hThread );
        return true;
    } catch( const std::exception & ) {
        error = "runtime_start_failed";
        return false;
    }
#else
    ( void )profile_id;
    ( void )api_key;
    error = "managed_runtime_requires_windows";
    return false;
#endif
}
} // namespace cata::actor_control
