#include "actor_control_files.h"

#include <algorithm>
#include <cerrno>
#include <climits>
#include <cwctype>
#include <string>
#include <vector>

#ifdef _WIN32
    #include "platform_win.h"
    #include <aclapi.h>
    #include <sddl.h>
    #include <fcntl.h>
    #include <io.h>
#else
    #include <fcntl.h>
    #include <sys/file.h>
    #include <sys/stat.h>
    #include <unistd.h>
#endif

namespace cata::actor_control::files
{
#ifdef _WIN32
namespace
{
int failed( DWORD code = GetLastError() )
{
    switch( code ) {
        case ERROR_FILE_NOT_FOUND:
        case ERROR_PATH_NOT_FOUND:
            errno = ENOENT;
            break;
        case ERROR_ALREADY_EXISTS:
        case ERROR_FILE_EXISTS:
            errno = EEXIST;
            break;
        case ERROR_SHARING_VIOLATION:
        case ERROR_LOCK_VIOLATION:
            errno = EAGAIN;
            break;
        case ERROR_ACCESS_DENIED:
            errno = EACCES;
            break;
        default:
            errno = EIO;
            break;
    }
    return -1;
}

// Win32 otherwise aliases streams, device names and trailing dots/spaces to
// different objects. The journal must address exactly the recorded filename.
bool valid_path( const std::filesystem::path &path )
{
    if( path.empty() || !path.is_absolute() ||
        path.native().find( L'\0' ) != std::wstring::npos ||
        path.native().compare( 0, 4, L"\\\\?\\" ) == 0 ||
        path.native().compare( 0, 4, L"\\\\.\\" ) == 0 ) {
        errno = EINVAL;
        return false;
    }
    for( const auto &part : path.relative_path() ) {
        const auto name = part.native();
        if( name.empty() || name.back() == L'.' || name.back() == L' ' ||
            name.find_first_of( L"<>:\"|?*" ) != std::wstring::npos ||
        std::any_of( name.begin(), name.end(), []( wchar_t c ) {
        return c < 32;
    } ) ) {
            errno = EINVAL;
            return false;
        }
        std::wstring stem = name.substr( 0, name.find( L'.' ) );
        std::transform( stem.begin(), stem.end(), stem.begin(), []( wchar_t c ) {
            return static_cast<wchar_t>( std::towupper( c ) );
        } );
        if( stem == L"CON" || stem == L"PRN" || stem == L"AUX" || stem == L"NUL" ||
            stem == L"CONIN$" || stem == L"CONOUT$" ||
            ( stem.size() == 4 && ( stem.compare( 0, 3, L"COM" ) == 0 ||
                                    stem.compare( 0, 3, L"LPT" ) == 0 ) &&
              ( ( stem[3] >= L'1' && stem[3] <= L'9' ) || stem[3] == L'\u00b9' ||
                stem[3] == L'\u00b2' || stem[3] == L'\u00b3' ) ) ) {
            errno = EINVAL;
            return false;
        }
    }
    auto prefix = path.root_path();
    for( const auto &part : path.parent_path().relative_path() ) {
        prefix /= part;
        const DWORD attributes = GetFileAttributesW( prefix.c_str() );
        if( attributes == INVALID_FILE_ATTRIBUTES ) {
            failed();
            return false;
        }
        if( !( attributes & FILE_ATTRIBUTE_DIRECTORY ) ||
            ( attributes & FILE_ATTRIBUTE_REPARSE_POINT ) ) {
            errno = EINVAL;
            return false;
        }
    }
    return true;
}

std::vector<unsigned char> user_token()
{
    HANDLE token = nullptr;
    if( !OpenProcessToken( GetCurrentProcess(), TOKEN_QUERY, &token ) ) {
        return {};
    }
    DWORD size = 0;
    GetTokenInformation( token, TokenUser, nullptr, 0, &size );
    std::vector<unsigned char> data( size );
    const bool ok = GetTokenInformation( token, TokenUser, data.data(), size, &size );
    CloseHandle( token );
    if( !ok ) {
        data.clear();
    }
    return data;
}

class private_security
{
    public:
        PSECURITY_DESCRIPTOR descriptor = nullptr;
        SECURITY_ATTRIBUTES attributes { sizeof( SECURITY_ATTRIBUTES ), nullptr, FALSE };
        private_security() {
            const auto token = user_token();
            if( token.empty() ) {
                return;
            }
            LPWSTR sid = nullptr;
            if( !ConvertSidToStringSidW( reinterpret_cast<const TOKEN_USER *>( token.data() )->User.Sid,
                                         &sid ) ) {
                return;
            }
            const std::wstring sddl = std::wstring( L"O:" ) + sid +
                                      L"D:P(A;;FA;;;SY)(A;;FA;;;" + sid + L")";
            LocalFree( sid );
            if( ConvertStringSecurityDescriptorToSecurityDescriptorW( sddl.c_str(),
                    SDDL_REVISION_1, &descriptor, nullptr ) ) {
                attributes.lpSecurityDescriptor = descriptor;
            }
        }
        ~private_security() {
            if( descriptor ) {
                LocalFree( descriptor );
            }
        }
        private_security( const private_security & ) = delete;
        private_security &operator=( const private_security & ) = delete;
};

bool private_handle( HANDLE handle )
{
    PSID owner = nullptr;
    PACL acl = nullptr;
    PSECURITY_DESCRIPTOR descriptor = nullptr;
    if( GetSecurityInfo( handle, SE_FILE_OBJECT, OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
                         &owner, nullptr, &acl, nullptr, &descriptor ) != ERROR_SUCCESS ) {
        return false;
    }
    const auto token = user_token();
    const PSID user = token.empty() ? nullptr :
                      reinterpret_cast<const TOKEN_USER *>( token.data() )->User.Sid;
    bool result = user && owner && EqualSid( user, owner ) && acl;
    for( DWORD index = 0; result && index < acl->AceCount; ++index ) {
        void *raw = nullptr;
        if( !GetAce( acl, index, &raw ) ) {
            result = false;
            break;
        }
        const auto ace = static_cast<ACCESS_ALLOWED_ACE *>( raw );
        if( ace->Header.AceType == ACCESS_DENIED_ACE_TYPE ) {
            continue;
        }
        result = ace->Header.AceType == ACCESS_ALLOWED_ACE_TYPE &&
                 ( EqualSid( user, const_cast<DWORD *>( &ace->SidStart ) ) ||
                   IsWellKnownSid( const_cast<DWORD *>( &ace->SidStart ), WinLocalSystemSid ) );
    }
    LocalFree( descriptor );
    return result;
}

int inspect_handle( HANDLE handle, info &result )
{
    BY_HANDLE_FILE_INFORMATION value {};
    if( !GetFileInformationByHandle( handle, &value ) ) {
        return failed();
    }
    result = {};
    if( !( value.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT ) ) {
        result.directory = value.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY;
        result.regular = !result.directory && GetFileType( handle ) == FILE_TYPE_DISK;
    }
    result.private_access = private_handle( handle );
    result.size = static_cast<std::int64_t>( ( static_cast<std::uint64_t>( value.nFileSizeHigh ) << 32 )
                  |
                  value.nFileSizeLow );
    result.links = value.nNumberOfLinks;
    return 0;
}
} // namespace

int inspect( const std::filesystem::path &path, info &result )
{
    if( !valid_path( path ) ) {
        return -1;
    }
    const HANDLE handle = CreateFileW( path.c_str(), FILE_READ_ATTRIBUTES | READ_CONTROL,
                                       FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr,
                                       OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS, nullptr );
    if( handle == INVALID_HANDLE_VALUE ) {
        return failed();
    }
    const int status = inspect_handle( handle, result );
    CloseHandle( handle );
    return status;
}

int inspect( int fd, info &result )
{
    return inspect_handle( reinterpret_cast<HANDLE>( _get_osfhandle( fd ) ), result );
}

int open( const std::filesystem::path &path, access mode )
{
    if( !valid_path( path ) ) {
        return -1;
    }
    private_security security;
    if( !security.descriptor ) {
        return failed();
    }
    const DWORD disposition = mode == access::create_new ? CREATE_NEW :
                              mode == access::read_write_create ? OPEN_ALWAYS : OPEN_EXISTING;
    const DWORD desired = GENERIC_READ | READ_CONTROL | ( mode == access::read ? 0 : GENERIC_WRITE );
    HANDLE handle = CreateFileW( path.c_str(), desired,
                                 FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, &security.attributes,
                                 disposition, FILE_FLAG_OPEN_REPARSE_POINT | FILE_ATTRIBUTE_NORMAL, nullptr );
    if( handle == INVALID_HANDLE_VALUE ) {
        return failed();
    }
    info value;
    if( inspect_handle( handle, value ) != 0 || !value.regular || value.links != 1 ) {
        CloseHandle( handle );
        errno = EINVAL;
        return -1;
    }
    const int fd = _open_osfhandle( reinterpret_cast<intptr_t>( handle ),
                                    _O_BINARY | _O_NOINHERIT | ( mode == access::read ? _O_RDONLY : _O_RDWR ) );
    if( fd < 0 ) {
        CloseHandle( handle );
    }
    return fd;
}

void close( int fd )
{
    _close( fd );
}
std::ptrdiff_t read( int fd, void *data, std::size_t size )
{
    return _read( fd, data, static_cast<unsigned int>( std::min<std::size_t>( size, INT_MAX ) ) );
}
std::ptrdiff_t write( int fd, const void *data, std::size_t size )
{
    return _write( fd, data, static_cast<unsigned int>( std::min<std::size_t>( size, INT_MAX ) ) );
}
int sync( int fd )
{
    return _commit( fd );
}
int sync_directory( const std::filesystem::path &path )
{
    // Windows has no directory fsync. Files are flushed before write-through
    // publication; keep the directory/reparse validation on both platforms.
    info value;
    if( inspect( path, value ) != 0 || !value.directory ) {
        errno = EINVAL;
        return -1;
    }
    return 0;
}
int lock( int fd )
{
    OVERLAPPED state {};
    return LockFileEx( reinterpret_cast<HANDLE>( _get_osfhandle( fd ) ),
                       LOCKFILE_EXCLUSIVE_LOCK | LOCKFILE_FAIL_IMMEDIATELY, 0, 1, 0, &state ) ? 0 : failed();
}
int replace( const std::filesystem::path &from, const std::filesystem::path &to )
{
    if( !valid_path( from ) || !valid_path( to ) ) {
        return -1;
    }
    return MoveFileExW( from.c_str(), to.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH ) ?
           0 : failed();
}
int remove( const std::filesystem::path &path )
{
    if( !valid_path( path ) ) {
        return -1;
    }
    return DeleteFileW( path.c_str() ) ? 0 : failed();
}
int create_private_directory( const std::filesystem::path &path )
{
    if( !valid_path( path ) ) {
        return -1;
    }
    private_security security;
    if( !security.descriptor ) {
        return failed();
    }
    if( !CreateDirectoryW( path.c_str(), &security.attributes ) &&
        GetLastError() != ERROR_ALREADY_EXISTS ) {
        return failed();
    }
    info value;
    if( inspect( path, value ) != 0 || !value.directory || !value.private_access ) {
        errno = EACCES;
        return -1;
    }
    return 0;
}
#else
namespace
{
void convert( const struct stat &source, info &result )
{
    result.regular = S_ISREG( source.st_mode );
    result.directory = S_ISDIR( source.st_mode );
    result.private_access = source.st_uid == getuid() &&
                            ( source.st_mode & 0777 ) == ( result.directory ? 0700 : 0600 );
    result.size = source.st_size;
    result.links = source.st_nlink;
}
} // namespace
int inspect( const std::filesystem::path &path, info &result )
{
    struct stat source {};
    const int status = lstat( path.c_str(), &source );
    if( status == 0 ) {
        convert( source, result );
    }
    return status;
}
int inspect( int fd, info &result )
{
    struct stat source {};
    const int status = fstat( fd, &source );
    if( status == 0 ) {
        convert( source, result );
    }
    return status;
}
int open( const std::filesystem::path &path, access mode )
{
    const int flags = mode == access::read ? O_RDONLY : mode == access::read_write ? O_RDWR :
                      mode == access::create_new ? O_RDWR | O_CREAT | O_EXCL : O_RDWR | O_CREAT;
    const int fd = ::open( path.c_str(), flags | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK, 0600 );
    struct stat value {};
    if( fd >= 0 && ( fstat( fd, &value ) != 0 || !S_ISREG( value.st_mode ) ||
                     value.st_nlink != 1 ) ) {
        ::close( fd );
        errno = EINVAL;
        return -1;
    }
    return fd;
}
void close( int fd )
{
    ::close( fd );
}
std::ptrdiff_t read( int fd, void *data, std::size_t size )
{
    return ::read( fd, data, size );
}
std::ptrdiff_t write( int fd, const void *data, std::size_t size )
{
    return ::write( fd, data, size );
}
int sync( int fd )
{
    return fsync( fd );
}
int sync_directory( const std::filesystem::path &path )
{
    const int fd = ::open( path.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC );
    if( fd < 0 ) {
        return -1;
    }
    const int status = fsync( fd );
    ::close( fd );
    return status;
}
int lock( int fd )
{
    return flock( fd, LOCK_EX | LOCK_NB );
}
int replace( const std::filesystem::path &from, const std::filesystem::path &to )
{
    return ::rename( from.c_str(), to.c_str() );
}
int remove( const std::filesystem::path &path )
{
    return unlink( path.c_str() );
}
int create_private_directory( const std::filesystem::path &path )
{
    if( mkdir( path.c_str(), 0700 ) != 0 && errno != EEXIST ) {
        return -1;
    }
    info value;
    if( inspect( path, value ) != 0 || !value.directory || !value.private_access ) {
        errno = EACCES;
        return -1;
    }
    return 0;
}
#endif
} // namespace cata::actor_control::files
