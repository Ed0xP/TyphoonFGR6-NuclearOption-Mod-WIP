import sys, dnfile
from dncil.cil.body import CilMethodBody
from dncil.cil.body.reader import CilMethodBodyReaderBase
from dncil.clr.token import Token, StringToken, InvalidToken
from dncil.cil.error import MethodBodyFormatError

class Reader(CilMethodBodyReaderBase):
    def __init__(self, pe, row):
        self.pe = pe; self.offset = pe.get_offset_from_rva(row.Rva)
    def read(self, n):
        d = self.pe.get_data(self.pe.get_rva_from_offset(self.offset), n); self.offset += n; return d
    def tell(self): return self.offset
    def seek(self, off): self.offset = off; return off

pe = dnfile.dnPE(sys.argv[1])
md = pe.net.mdtables
def tname(tbl, idx):
    try:
        r = tbl[idx - 1]
        return (r.TypeNamespace + "." if getattr(r, 'TypeNamespace', '') else "") + r.TypeName
    except Exception: return "?"
def resolve(tok):
    t = tok.table; i = tok.rid
    try:
        if t == 0x0A:
            r = md.MemberRef[i - 1]
            cls = r.Class
            try: cn = cls.row.TypeName
            except Exception: cn = "?"
            return f"{cn}::{r.Name}"
        if t == 0x06:
            r = md.MethodDef[i - 1]
            return f"{owner_of_method.get(i,'?')}::{r.Name}"
        if t == 0x04:
            r = md.Field[i - 1]; return f"{owner_of_field.get(i,'?')}::{r.Name}"
        if t == 0x01: return md.TypeRef[i - 1].TypeName
        if t == 0x02: return md.TypeDef[i - 1].TypeName
        if t == 0x2B:
            r = md.MethodSpec[i - 1]
            try: return "spec:" + r.Method.row.Name
            except Exception: return "methodspec"
        if t == 0x1B: return "typespec"
        if t == 0x70:
            return '"' + str(pe.net.user_strings.get(i)) + '"'
    except Exception as e:
        return f"tok{t:x}:{i}"
    return f"tok{t:x}:{i}"
owner_of_method = {}; owner_of_field = {}
tds = list(md.TypeDef)
for ti, td in enumerate(tds):
    for m in td.MethodList: owner_of_method[m.row_index] = td.TypeName
    for f in td.FieldList: owner_of_field[f.row_index] = td.TypeName
want = sys.argv[2:]
for td in tds:
    for w in want:
        tn, _, mn = w.partition('.')
        if td.TypeName != tn: continue
        for mref in td.MethodList:
            m = mref.row
            if mn and m.Name != mn: continue
            if not m.Rva: continue
            try:
                body = CilMethodBody(Reader(pe, m))
            except MethodBodyFormatError as e:
                print("bad body", m.Name); continue
            print(f"=== {tn}::{m.Name}")
            for ins in body.instructions:
                op = ins.operand
                s = ""
                if isinstance(op, StringToken): s = '"' + str(pe.net.user_strings.get(op.rid)) + '"'
                elif isinstance(op, Token): s = resolve(op)
                elif op is not None: s = str(op)
                print(f"  {ins.offset:04x} {ins.opcode.name:10s} {s}")
