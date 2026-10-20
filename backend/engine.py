"""Decimal formula interpreter. No eval; explicit grammar and dependency graph."""
from decimal import Decimal, InvalidOperation
import re
from time import perf_counter

class FormulaError(ValueError): pass

TOKEN = re.compile(r'\s*(?:(\d+(?:\.\d*)?|\.\d+)|([A-Za-z]+\d+|[A-Za-z_]+)|([+*/^(),:\-]))')
CELL = re.compile(r'^[A-Z]+[1-9]\d*$')

def coordinates(cell):
    m = re.fullmatch(r'([A-Z]+)([1-9]\d*)', cell)
    if not m: raise FormulaError('Invalid reference')
    col = 0
    for c in m[1]: col = col * 26 + ord(c) - 64
    return col, int(m[2])

def column(n):
    out = ''
    while n:
        n, r = divmod(n-1, 26); out = chr(65+r)+out
    return out

class Parser:
    def __init__(self, raw):
        raw = raw.lstrip('='); self.tokens=[]; self.i=0; self.refs=set()
        if len(raw)>2000: raise FormulaError('Formula too long')
        pos=0
        while pos<len(raw.rstrip()):
            m=TOKEN.match(raw,pos)
            if not m: raise FormulaError(f'Unexpected character at {pos+1}')
            self.tokens.append(next(x for x in m.groups() if x is not None).upper()); pos=m.end()
    def peek(self): return self.tokens[self.i] if self.i<len(self.tokens) else ''
    def take(self, expected=None):
        x=self.peek()
        if not x or expected and x!=expected: raise FormulaError(f'Expected {expected or "expression"}')
        self.i+=1; return x
    def parse(self):
        try: tree=self.expr()
        except RecursionError: raise FormulaError('Expression too deeply nested')
        if self.peek(): raise FormulaError('Unexpected token '+self.peek())
        return tree
    def expr(self, minimum=0):
        t=self.take()
        if t in ('+','-'): left=('unary',t,self.expr(25))
        elif t=='(':
            left=self.expr(); self.take(')')
        elif CELL.fullmatch(t):
            if self.peek()==':':
                self.take(':'); end=self.take(); c1,r1=coordinates(t); c2,r2=coordinates(end)
                if (abs(c2-c1)+1)*(abs(r2-r1)+1)>10000: raise FormulaError('Range too large')
                refs=[column(c)+str(r) for r in range(min(r1,r2),max(r1,r2)+1) for c in range(min(c1,c2),max(c1,c2)+1)]
                if len(refs)>10000: raise FormulaError('Range too large')
                self.refs.update(refs); left=('range',refs)
            else: self.refs.add(t); left=('ref',t)
        elif re.match(r'^\d|^\.',t): left=('num',Decimal(t))
        elif t in ('SUM','AVG','MIN','MAX','ABS','ROUND','IF'):
            self.take('('); args=[]
            if self.peek()!=')':
                args.append(self.expr())
                while self.peek()==',': self.take(','); args.append(self.expr())
            self.take(')'); left=('call',t,args)
        else: raise FormulaError('Unknown name '+t)
        while self.peek() in ('+','-','*','/','^'):
            op=self.peek(); precedence={'+':10,'-':10,'*':20,'/':20,'^':30}[op]
            if precedence<minimum: break
            self.take(); right=self.expr(precedence if op=='^' else precedence+1); left=('binary',op,left,right)
        return left

def evaluate(node, values):
    kind=node[0]
    if kind=='num': return node[1]
    if kind=='ref':
        v=values.get(node[1],Decimal(0))
        if isinstance(v,str): raise FormulaError('Dependency error: '+v)
        return v
    if kind=='range': return [evaluate(('ref',r),values) for r in node[1]]
    if kind=='unary': return evaluate(node[2],values)*(1 if node[1]=='+' else -1)
    if kind=='binary':
        a,b=evaluate(node[2],values),evaluate(node[3],values); op=node[1]
        if isinstance(a,list) or isinstance(b,list): raise FormulaError('Range needs a function')
        if op=='+': return a+b
        if op=='-': return a-b
        if op=='*': return a*b
        if op=='/':
            if b==0: raise FormulaError('#DIV/0!')
            return a/b
        if abs(b)>100: raise FormulaError('Exponent exceeds limit')
        return a**b
    name,args=node[1:]
    if name=='IF':
        if len(args)!=3: raise FormulaError('IF needs 3 arguments')
        return evaluate(args[1] if evaluate(args[0],values) else args[2],values)
    flat=[]
    for arg in args:
        v=evaluate(arg,values); flat.extend(v if isinstance(v,list) else [v])
    if not flat: raise FormulaError('Function needs arguments')
    if name=='SUM': return sum(flat,Decimal(0))
    if name=='AVG': return sum(flat,Decimal(0))/len(flat)
    if name=='MIN': return min(flat)
    if name=='MAX': return max(flat)
    if name=='ABS' and len(flat)==1: return abs(flat[0])
    if name=='ROUND' and len(flat) in (1,2):
        digits=int(flat[1]) if len(flat)==2 else 0
        if abs(digits)>20: raise FormulaError('ROUND precision exceeds limit')
        return flat[0].quantize(Decimal(10)**-digits)
    raise FormulaError('Invalid arguments')

class Engine:
    def __init__(self, cells=None):
        self.raw={}; self.ast={}; self.deps={}; self.reverse={}; self.values={}
        for cell,raw in (cells or {}).items(): self.set(cell,raw)
    def set(self,cell,raw):
        cell=cell.upper(); coordinates(cell); raw=str(raw).strip()
        if len(raw)>2000: raise FormulaError('Cell too long')
        start=perf_counter(); parser=Parser(raw) if raw.startswith('=') else None
        tree=parser.parse() if parser else ('num',Decimal(raw or '0'))
        refs=parser.refs if parser else set()
        # Validate against proposed graph before any mutation.
        pending=list(refs); visited=set()
        while pending:
            ref=pending.pop()
            if ref==cell: raise FormulaError('#CYCLE! Edit would create a circular reference')
            if ref not in visited: visited.add(ref); pending.extend(self.deps.get(ref,()))
        for ref in self.deps.get(cell,set()): self.reverse[ref].discard(cell)
        self.raw[cell]=raw; self.ast[cell]=tree; self.deps[cell]=refs
        for ref in refs: self.reverse.setdefault(ref,set()).add(cell)
        affected={cell}; pending=[cell]
        while pending:
            for child in self.reverse.get(pending.pop(),()):
                if child not in affected: affected.add(child); pending.append(child)
        indegree={c:len(self.deps.get(c,set()) & affected) for c in affected}
        ready=[c for c,d in indegree.items() if d==0]; order=[]
        while ready:
            c=ready.pop(); order.append(c)
            try:
                value=evaluate(self.ast[c],self.values)
                if isinstance(value,list): raise FormulaError('Range needs a function')
                if not value.is_finite(): raise FormulaError('Non-finite result')
                self.values[c]=value
            except (ArithmeticError,FormulaError,TypeError,ValueError,RecursionError) as exc: self.values[c]=str(exc)
            for child in self.reverse.get(c,()):
                if child in indegree:
                    indegree[child]-=1
                    if indegree[child]==0: ready.append(child)
        return {'affected':order,'recalculated':len(order),'duration_ms':round((perf_counter()-start)*1000,3)}
    def snapshot(self):
        return {c:{'raw':r,'value':str(self.values.get(c,0)),'dependencies':sorted(self.deps.get(c,[])),'dependents':sorted(self.reverse.get(c,[]))} for c,r in self.raw.items()}
