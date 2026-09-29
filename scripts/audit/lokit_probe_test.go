// Injected characterization tests for lokit a28493ba832ffc5506d4e45f4ddfdc5623931aa9.
// This file is original test code, not a copy or patch of lokit's implementation.
package translate

import (
    "bytes"
    "context"
    "encoding/json"
    "fmt"
    "io"
    "net/http"
    "net/http/httptest"
    "os"
    "reflect"
    "strings"
    "testing"

    po "github.com/minios-linux/lokit/internal/format/po"
)

type auditFixture struct {
    Name string `json:"name"`
    Context *string `json:"context"`
    MsgID string `json:"msgid"`
    Plural *string `json:"plural"`
    Translations []string `json:"translations"`
    Comments string `json:"comments"`
    Occurrences [][]string `json:"occurrences"`
}
func auditFixtures(t *testing.T) []auditFixture {
    t.Helper()
    b, err := os.ReadFile(os.Getenv("PO_MAINTAIN_AUDIT_FIXTURE"))
    if err != nil { t.Fatal(err) }
    var f []auditFixture
    if err = json.Unmarshal(b, &f); err != nil { t.Fatal(err) }
    return f
}
func auditEntry(f auditFixture) *po.Entry {
    e := &po.Entry{MsgID:f.MsgID, ExtractedComments:[]string{f.Comments}, TranslatorComments:[]string{"Translator marker: " + f.Name}}
    if f.Context != nil { e.MsgCtxt = *f.Context }
    if f.Plural != nil { e.MsgIDPlural = *f.Plural }
    for _, o := range f.Occurrences { e.References = append(e.References, strings.Join(o, ":")) }
    return e
}
func auditJSON(v any) string { b, _ := json.Marshal(v); return string(b) }
func auditResponse(entries []*po.Entry, translations []any) string {
    ids := entryTranslationIDs(entries)
    items := make([]map[string]any, len(entries))
    for i := range entries { items[i] = map[string]any{"id":ids[i], "translation":translations[i]} }
    for i, j := 0, len(items)-1; i < j; i, j = i+1, j-1 { items[i], items[j] = items[j], items[i] }
    return auditJSON(map[string]any{"candidates":[]any{map[string]any{"content":map[string]any{"parts":[]any{map[string]any{"text":auditJSON(items)}}}}}})
}
func auditServer(t *testing.T, response string, captured *string, calls *int) *httptest.Server {
    t.Helper()
    return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        *calls++
        if r.URL.Path != "/v1beta/models/fake-model:generateContent" { t.Errorf("wrong Gemini route: %s", r.URL.Path) }
        if r.Header.Get("x-goog-api-key") != "fake-key" { t.Error("missing fake Google API key header") }
        b, _ := io.ReadAll(r.Body); *captured = string(b)
        w.Header().Set("Content-Type", "application/json")
        fmt.Fprint(w, response)
    }))
}
func auditOptions(url string) Options {
    return Options{LanguageName:"Polish", MaxRetries:0, Provider:Provider{ID:ProviderGoogle, Name:"google", BaseURL:url, Model:"fake-model", APIKey:"fake-key"}}
}
func TestAuditSharedFixturesGoogleAndPromptWrapper(t *testing.T) {
    fixtures := auditFixtures(t)
    var entries []*po.Entry
    var values []any
    for _, f := range fixtures {
        entries = append(entries, auditEntry(f))
        if f.Plural == nil { values = append(values, f.Translations[0]) } else { values = append(values, f.Translations) }
    }
    captured := ""; calls := 0
    s := auditServer(t, auditResponse(entries, values), &captured, &calls); defer s.Close()
    opts := auditOptions(s.URL)
    got, err := translateChunkWithPlurals(context.Background(), entries, "base prompt", opts, nil, 3)
    if err != nil { t.Fatal(err) }
    for i, f := range fixtures {
        if f.Plural == nil && got[i].singular != f.Translations[0] { t.Fatalf("%s changed translation", f.Name) }
        if f.Plural != nil && !reflect.DeepEqual(got[i].plural, f.Translations) { t.Fatalf("%s changed plural", f.Name) }
    }
    for _, marker := range []string{"audit:verb", "Developer marker:", "Translator marker:"} {
        if strings.Contains(captured, marker) { t.Fatalf("pinned expected omission changed: %s", marker) }
    }
    if !strings.Contains(captured, "src/ui.c:12") { t.Fatal("references absent") }
    t.Log("OBSERVED: Google native HTTP, shared valid fixtures accepted; context and both comment types omitted; references present")
    // Existing prompt override can carry sidecar metadata per bounded group.
    _, err = translateChunkWithPlurals(context.Background(), entries, "Group metadata: " + auditJSON(fixtures), opts, nil, 3)
    if err != nil { t.Fatal(err) }
    for _, marker := range []string{"audit:verb", "Developer marker:"} {
        if !strings.Contains(captured, marker) { t.Fatalf("wrapper prompt missing %s", marker) }
    }
    t.Log("OBSERVED: custom prompt can supply context and comments without patching lokit")
}
func TestAuditExplicitEmptyContextLoss(t *testing.T) {
    fixtures := auditFixtures(t)
    var raw strings.Builder
    for _, f := range fixtures[:2] {
        if f.Context != nil { fmt.Fprintf(&raw, "msgctxt %s\n", auditJSON(*f.Context)) }
        fmt.Fprintf(&raw, "msgid %s\nmsgstr %s\n\n", auditJSON(f.MsgID), auditJSON(f.Translations[0]))
    }
    f, err := po.Parse(strings.NewReader(raw.String())); if err != nil { t.Fatal(err) }
    var out bytes.Buffer; if err = f.Write(&out); err != nil { t.Fatal(err) }
    if strings.Contains(out.String(), "msgctxt") { t.Fatal("pinned expected empty context loss changed") }
    t.Log("OBSERVED: explicit msgctxt empty is omitted on parse/write; external identity sidecar required")
}
func TestAuditPluralNormalization(t *testing.T) {
    f := auditFixtures(t)[4]; entries := []*po.Entry{auditEntry(f)}
    cases := []struct{name string; raw any; want []string}{
        {"scalar", f.Translations[0], []string{f.Translations[0],f.Translations[0],f.Translations[0]}},
        {"short", f.Translations[:2], []string{f.Translations[0],f.Translations[1],f.Translations[1]}},
        {"long", append(append([]string{}, f.Translations...), "EXTRA"), f.Translations},
    }
    for _, c := range cases { t.Run(c.name, func(t *testing.T) {
        captured := ""; calls := 0
        s := auditServer(t, auditResponse(entries, []any{c.raw}), &captured, &calls); defer s.Close()
        got, err := translateChunkWithPlurals(context.Background(), entries, "strict: exactly 3 forms", auditOptions(s.URL), nil, 3)
        if err != nil { t.Fatal(err) }
        if !reflect.DeepEqual(got[0].plural, c.want) { t.Fatalf("changed behavior: %#v", got) }
        if calls != 1 { t.Fatalf("calls=%d", calls) }
        t.Logf("OBSERVED: malformed %s plural response silently accepted after normalization", c.name)
    }) }
}
func TestAuditRetriesZeroAndIDs(t *testing.T) {
    f := auditFixtures(t)[2]; entries := []*po.Entry{auditEntry(f)}
    captured := ""; calls := 0
    s := auditServer(t, `{"candidates":[{"content":{"parts":[{"text":"[]"}]}}]}`, &captured, &calls); defer s.Close()
    _, err := translateChunk(context.Background(), entries, "base", auditOptions(s.URL), nil)
    if err == nil { t.Fatal("invalid correspondence accepted") }
    if calls != 4 { t.Fatalf("MaxRetries=0 calls=%d, expected pinned behavior 4", calls) }
    t.Log("OBSERVED: wrong response count rejected; MaxRetries=0 performs 4 requests (initial + 3 retries)")
    ids := entryTranslationIDs(entries)
    for _, response := range []string{
        `[{"id":"unknown","translation":"x"}]`,
        fmt.Sprintf(`[{"id":%q,"translation":"x"},{"id":%q,"translation":"x"}]`, ids[0],ids[0]),
    } { if _, err = parseIdentifiedTranslations(response, ids); err == nil { t.Fatal("bad IDs accepted") } }
}
