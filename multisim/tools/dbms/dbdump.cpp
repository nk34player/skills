// dbdump.cpp - dump the Multisim Jet databases to TSV, fast.
//
// The master component database is a Jet 3 (Access 97) file. ACE/the 64-bit Access
// driver refuses it ("created with a previous version"), but the 32-bit Jet 4.0 ODBC
// driver "Microsoft Access Driver (*.mdb)" reads it fine. So this tool must be built
// x86 and run from a 32-bit process:
//
//   call vcvars32.bat && cl /O2 /EHsc /nologo dbdump.cpp odbc32.lib
//   dbdump.exe <db.usr|.PRD> <outdir>
//
// Output: one <TABLE>.tsv per table (tab separated, \r\n inside cells escaped as \n,
// tabs as \t, backslash as \\). Column names on the first line.
#include <windows.h>
#include <sql.h>
#include <sqlext.h>
#include <stdio.h>
#include <string>
#include <vector>

static std::string esc(const char *p, SQLLEN n) {
    std::string o;
    for (SQLLEN i = 0; i < n; i++) {
        char c = p[i];
        if (c == '\\') o += "\\\\";
        else if (c == '\t') o += "\\t";
        else if (c == '\r') o += "\\r";
        else if (c == '\n') o += "\\n";
        else o += c;
    }
    return o;
}

static void diag(SQLSMALLINT type, SQLHANDLE h, const char *what) {
    SQLCHAR state[7], msg[512];
    SQLINTEGER native;
    SQLSMALLINT len;
    for (SQLSMALLINT i = 1; SQLGetDiagRec(type, h, i, state, &native, msg, sizeof msg, &len) == SQL_SUCCESS; i++)
        fprintf(stderr, "%s: [%s] %s\n", what, state, msg);
}

static bool exec(SQLHDBC dbc, const std::string &sql, SQLHSTMT *out) {
    SQLHSTMT stmt;
    if (!SQLAllocHandle(SQL_HANDLE_STMT, dbc, &stmt)) {
        if (SQLExecDirect(stmt, (SQLCHAR *)sql.c_str(), SQL_NTS) == SQL_SUCCESS) { *out = stmt; return true; }
        diag(SQL_HANDLE_STMT, stmt, sql.c_str());
        SQLFreeHandle(SQL_HANDLE_STMT, stmt);
    }
    return false;
}

static int dumpTable(SQLHDBC dbc, const char *table, const std::string &outdir) {
    SQLHSTMT stmt;
    std::string sql = std::string("SELECT * FROM [") + table + "]";
    if (!exec(dbc, sql, &stmt)) return 0;

    SQLSMALLINT ncols = 0;
    SQLNumResultCols(stmt, &ncols);
    std::string path = outdir + "\\" + table + ".tsv";
    FILE *f = fopen(path.c_str(), "wb");
    if (!f) { fprintf(stderr, "cannot write %s\n", path.c_str()); return 0; }

    for (SQLSMALLINT c = 1; c <= ncols; c++) {
        SQLCHAR name[256]; SQLSMALLINT nlen = 0;
        SQLDescribeCol(stmt, c, name, sizeof name, &nlen, 0, 0, 0, 0);
        fputs(c > 1 ? "\t" : "", f);
        fwrite(name, 1, nlen, f);
    }
    fputs("\n", f);

    std::vector<SQLLEN> ind(ncols);
    std::vector<char> buf(1 << 20);
    long rows = 0;
    while (SQLFetch(stmt) == SQL_SUCCESS) {
        for (SQLSMALLINT c = 1; c <= ncols; c++) {
            SQLSMALLINT ctype = 0, dtype = 0, digits = 0, nullable = 0;
            SQLULEN collen = 0;
            SQLDescribeCol(stmt, c, 0, 0, 0, &dtype, &collen, &digits, &nullable);
            ctype = (dtype == SQL_BINARY || dtype == SQL_VARBINARY || dtype == SQL_LONGVARBINARY ||
                     dtype == SQL_LONGVARCHAR || dtype == SQL_WLONGVARCHAR) ? SQL_C_BINARY : SQL_C_CHAR;
            if (collen + 1 > buf.size()) buf.resize(collen + 1);
            if (SQLGetData(stmt, c, ctype, buf.data(), (SQLLEN)buf.size(), &ind[c]) != SQL_SUCCESS &&
                ind[c] == SQL_NULL_DATA) {}
            if (c > 1) fputc('\t', f);
            if (ind[c] == SQL_NULL_DATA) continue;
            size_t n = (size_t)ind[c];
            if (ctype == SQL_C_CHAR) {                    // NUL terminated
                n = 0;
                while (n < buf.size() && buf[n]) n++;
            } else {                                      // hex for binaries
                fputc('x', f);
                for (size_t i = 0; i < n; i++) fprintf(f, "%02x", (unsigned char)buf[i]);
                continue;
            }
            std::string s = esc(buf.data(), (SQLLEN)n);
            fwrite(s.data(), 1, s.size(), f);
        }
        fputc('\n', f);
        rows++;
    }
    fclose(f);
    SQLFreeHandle(SQL_HANDLE_STMT, stmt);
    printf("%-28s %8ld rows\n", table, rows);
    return 1;
}

int main(int argc, char **argv) {
    if (argc < 3) { fprintf(stderr, "usage: dbdump <db> <outdir>\n"); return 2; }
    std::string dsn = std::string("DRIVER={Microsoft Access Driver (*.mdb)};DBQ=") + argv[1] + ";";
    SQLHENV env; SQLHDBC dbc;
    SQLAllocHandle(SQL_HANDLE_ENV, 0, &env);
    SQLSetEnvAttr(env, SQL_ATTR_ODBC_VERSION, (void *)SQL_OV_ODBC3, 0);
    SQLAllocHandle(SQL_HANDLE_DBC, env, &dbc);
    if (SQLDriverConnect(dbc, 0, (SQLCHAR *)dsn.c_str(), SQL_NTS, 0, 0, 0, SQL_DRIVER_NOPROMPT) != SQL_SUCCESS) {
        diag(SQL_HANDLE_DBC, dbc, "connect");
        return 1;
    }
    CreateDirectoryA(argv[2], 0);   // one level, caller's choice
    const char *tables[] = {
        "SYS_COMPONENT", "SYS_CONFIGURATION", "SYS_CONFIGURATION_GROUPS", "SYS_KIND",
        "SYS_MAPPING_COMP_MODEL", "SYS_MODEL", "SYS_MAPPING_COMP_SYMBOL", "SYS_INFO",
    };
    int ok = 0;
    for (const char *t : tables) ok += dumpTable(dbc, t, argv[2]);
    SQLDisconnect(dbc);
    SQLFreeHandle(SQL_HANDLE_DBC, dbc);
    SQLFreeHandle(SQL_HANDLE_ENV, env);
    return ok == (int)(sizeof tables / sizeof *tables) ? 0 : 1;
}
