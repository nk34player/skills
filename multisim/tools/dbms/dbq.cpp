// dbq.cpp - query the Multisim component database from its TSV dump.
//
// The Jet file itself needs a Python page parser (tools/dbms/jet2tsv.py, one-time).
// This tool is the fast path used by every circuit build: it loads the TSV dump into
// memory in well under a second and answers part queries.
//
//   call vcvars32.bat && cl /O2 /EHsc /nologo dbq.cpp /Fe:dbq.exe
//
//   dbq search <substr> [limit]     name, pin count, family, function
//   dbq show   <name>               full record incl. SPICE model card
//   dbq json   <name>               machine-readable record (used by multisim_db.py)
//   dbq fam                         family table (Family_ID -> name, group)
//
// Lookup dir: $MSDB_DUMP, else <exe dir>\dump
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <map>
#include <unordered_map>
#ifdef _WIN32
#include <windows.h>
#endif

// ------------------------------------------------------------------ tsv -----
struct Cell { size_t off, len; };   // slice of the shared text blob

static std::string unesc(const char *p, size_t n) {
    std::string o;
    o.reserve(n);
    for (size_t i = 0; i < n; i++) {
        if (p[i] != '\\' || i + 1 >= n) { o += p[i]; continue; }
        char c = p[++i];
        o += c == 'n' ? '\n' : c == 'r' ? '\r' : c == 't' ? '\t' : c;
    }
    return o;
}

struct Table {
    std::string text;                 // this table's own blob (offsets are per-file)
    std::vector<std::string> col;
    std::vector<std::vector<Cell>> row;
    int idx(const char *name) const {
        for (size_t i = 0; i < col.size(); i++)
            if (!_stricmp(col[i].c_str(), name)) return (int)i;
        return -1;
    }
    std::string get(size_t r, int c) const {
        if (c < 0 || r >= row.size() || (size_t)c >= row[r].size()) return "";
        const Cell &x = row[r][c];
        return unesc(text.data() + x.off, x.len);
    }
};

static bool load(const std::string &path, Table &t) {
    FILE *f = fopen(path.c_str(), "rb");
    if (!f) return false;
    fseek(f, 0, SEEK_END); long sz = ftell(f); fseek(f, 0, SEEK_SET);
    t.text.resize((size_t)sz);
    size_t got = fread(&t.text[0], 1, (size_t)sz, f);
    fclose(f);
    t.text.resize(got);

    // column header
    size_t pos = 0;
    while (pos < t.text.size()) {
        size_t e = t.text.find('\n', pos);
        if (e == std::string::npos) e = t.text.size();
        std::string line = t.text.substr(pos, e - pos);
        if (!t.col.empty()) break;                       // header only once
        size_t s = 0;
        while (s <= line.size()) {
            size_t u = line.find('\t', s);
            if (u == std::string::npos) u = line.size();
            t.col.push_back(line.substr(s, u - s));
            if (u == line.size()) break;
            s = u + 1;
        }
        pos = e + 1;
    }
    while (pos < t.text.size()) {
        size_t e = t.text.find('\n', pos);
        if (e == std::string::npos) e = t.text.size();
        std::vector<Cell> cells;
        size_t s = pos;
        while (s < e) {
            size_t u = s;
            while (u < e && t.text[u] != '\t') u++;
            cells.push_back({s, u - s});
            s = u + 1;
        }
        t.row.push_back(std::move(cells));
        pos = e + 1;
    }
    return true;
}

static std::string dirOf(const char *argv0) {
    if (const char *e = getenv("MSDB_DUMP")) return std::string(e);
    std::string a = argv0;
    size_t p = a.find_last_of("\\/");
    return (p == std::string::npos ? std::string(".") : a.substr(0, p)) + "\\dump";
}

static void jstr(const std::string &s) {
    putchar('"');
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') { putchar('\\'); putchar(c); }
        else if (c == '\n') fputs("\\n", stdout);
        else if (c == '\r') fputs("\\r", stdout);
        else if (c == '\t') fputs("\\t", stdout);
        else if (c < 32) fprintf(stdout, "\\u%04x", c);
        else putchar(c);
    }
    putchar('"');
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr,
            "usage: dbq search <substr> [limit]\n"
            "       dbq show <name>\n"
            "       dbq json <name>\n"
            "       dbq fam\n");
        return 2;
    }
    const std::string dir = dirOf(argv[0]);
    Table comp, fams, cmap, model;
    if (!load(dir + "\\SYS_COMPONENT.tsv", comp)) { fprintf(stderr, "no dump in %s\n", dir.c_str()); return 1; }
    load(dir + "\\SYS_CONFIGURATION.tsv", fams);
    load(dir + "\\SYS_MAPPING_COMP_MODEL.tsv", cmap);
    load(dir + "\\SYS_MODEL.tsv", model);

    const int cId = comp.idx("Component_ID"), cName = comp.idx("Component_Name"),
              cFam = comp.idx("Family_ID"), cPins = comp.idx("Pin_Number"),
              cFunc = comp.idx("Function"), cMan = comp.idx("Manufacturer"),
              cDesc = comp.idx("Description"), cPinout = comp.idx("Pinout"),
              cPinFam = comp.idx("Pin_Family"), cKind = comp.idx("Kind_ID");

    const int fId = fams.idx("Family_ID"), fName = fams.idx("Family_Name"),
              fGroup = fams.idx("Family_Group_ID"), fTpl = fams.idx("Template");

    std::string cmd = argv[1];

    if (cmd == "fam") {
        for (size_t r = 0; r < fams.row.size(); r++)
            printf("%-4s %-34s grp=%-3s %s\n", fams.get(r, fId).c_str(),
                   fams.get(r, fName).c_str(), fams.get(r, fGroup).c_str(),
                   fams.get(r, fTpl).c_str());
        return 0;
    }

    if (argc < 3) { fprintf(stderr, "need a part name\n"); return 2; }

    // index: component name -> row
    std::unordered_map<std::string, size_t> byName;
    for (size_t r = 0; r < comp.row.size(); r++) byName.emplace(comp.get(r, cName), r);

    if (cmd == "search") {
        std::string q = argv[2];
        for (auto &c : q) c = (char)toupper((unsigned char)c);
        int limit = argc > 3 ? atoi(argv[3]) : 30;
        for (size_t r = 0; r < comp.row.size() && limit > 0; r++) {
            std::string n = comp.get(r, cName);
            std::string u = n;
            for (auto &c : u) c = (char)toupper((unsigned char)c);
            if (u.find(q) == std::string::npos) continue;
            printf("%-28s pins=%-2s fam=%-4s %s\n", n.c_str(), comp.get(r, cPins).c_str(),
                   comp.get(r, cFam).c_str(), comp.get(r, cFunc).substr(0, 60).c_str());
            limit--;
        }
        return 0;
    }

    auto it = byName.find(argv[2]);
    if (it == byName.end()) { fprintf(stderr, "no such part: %s\n", argv[2]); return 1; }
    size_t r = it->second;
    const std::string cid = comp.get(r, cId);

    // model + template for this component
    const int mCid = cmap.idx("Component_ID"), mModel = cmap.idx("MODEL_ID"), mTpl = cmap.idx("Template");
    std::string mid, tpl;
    for (size_t i = 0; i < cmap.row.size(); i++)
        if (cmap.get(i, mCid) == cid) { mid = cmap.get(i, mModel); tpl = cmap.get(i, mTpl); break; }

    std::string spice;
    const int dId = model.idx("MODEL_ID"), dData = model.idx("DATA");
    for (size_t i = 0; i < model.row.size(); i++)
        if (model.get(i, dId) == mid) { spice = model.get(i, dData); break; }

    if (cmd == "json") {
        printf("{\n");
        printf("  \"name\": ");         jstr(comp.get(r, cName));        printf(",\n");
        printf("  \"id\": %s,\n", cid.c_str());
        printf("  \"family\": %s,\n", comp.get(r, cFam).c_str());
        printf("  \"kind\": %s,\n", comp.get(r, cKind).c_str());
        printf("  \"pins\": %s,\n", comp.get(r, cPins).c_str());
        printf("  \"pin_family\": ");   jstr(comp.get(r, cPinFam));      printf(",\n");
        printf("  \"pinout\": ");       jstr(comp.get(r, cPinout));      printf(",\n");
        printf("  \"manufacturer\": "); jstr(comp.get(r, cMan));         printf(",\n");
        printf("  \"function\": ");     jstr(comp.get(r, cFunc));        printf(",\n");
        printf("  \"description\": ");  jstr(comp.get(r, cDesc));        printf(",\n");
        printf("  \"model\": ");        jstr(mid);                       printf(",\n");
        printf("  \"template\": ");     jstr(tpl);                       printf(",\n");
        printf("  \"spice\": ");        jstr(spice);                     printf("\n}\n");
        return 0;
    }

    // show
    printf("name       : %s\n", comp.get(r, cName).c_str());
    printf("family     : %s\n", comp.get(r, cFam).c_str());
    printf("kind       : %s\n", comp.get(r, cKind).c_str());
    printf("pins       : %s  pin_family=%s\n", comp.get(r, cPins).c_str(), comp.get(r, cPinFam).c_str());
    printf("pinout     : %s\n", comp.get(r, cPinout).c_str());
    printf("manufacturer: %s\n", comp.get(r, cMan).c_str());
    printf("function   : %s\n", comp.get(r, cFunc).c_str());
    printf("description: %s\n", comp.get(r, cDesc).c_str());
    printf("model      : %s\n", mid.c_str());
    printf("template   : %s\n", tpl.c_str());
    printf("spice      : %s\n", spice.empty() ? "<none>" : spice.c_str());
    return 0;
}
