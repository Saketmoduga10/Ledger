from decimal import Decimal
import pytest
from engine import Engine, FormulaError

def test_precedence_and_functions():
    e=Engine({'A1':'5','A2':'3','B1':'=SUM(A1:A2)*2+2^3','B2':'=IF(0,1/0,ROUND(2.345,2))'})
    assert e.values['B1']==24
    assert e.values['B2']==Decimal('2.34')
    e.set('C1','=-2^2'); assert e.values['C1']==-4

def test_incremental_diamond():
    e=Engine({'A1':'2','B1':'=A1*2','C1':'=A1+1','D1':'=B1+C1','Z1':'999'})
    stats=e.set('A1','4')
    assert set(stats['affected'])=={'A1','B1','C1','D1'}
    assert e.values['D1']==13

def test_cycle_atomic_and_dependency_rewire():
    e=Engine({'A1':'1','B1':'=A1','C1':'=B1'})
    with pytest.raises(FormulaError): e.set('A1','=C1')
    assert e.raw['A1']=='1'
    e.set('B1','7'); assert e.set('A1','9')['affected']==['A1']
    assert e.values['C1']==7

def test_errors_recover_and_forward_refs():
    e=Engine({'B1':'=A1/0','C1':'=B1+1','A1':'10'})
    assert '#DIV/0!' in e.values['B1']
    e.set('B1','=A1/2'); assert e.values['C1']==6
    with pytest.raises(FormulaError): e.set('D1','=__import__(1)')

def test_decimal_finance():
    e=Engine({'A1':'0.1','B1':'=A1+0.2'})
    assert e.values['B1']==Decimal('0.3')

def test_power_range_limits_and_bad_names():
    e=Engine()
    for formula in ['=SUM(A1:ZZ99999)','=SUM(A1:A99999999)','=foo(2)','=1;2']:
        with pytest.raises(FormulaError): e.set('A1',formula)


def test_random_dag_matches_full_recompute():
    import random
    from engine import evaluate
    random.seed(42)
    raw={'A1':'1'}
    for i in range(2,120):
        a,b=random.randrange(1,i),random.randrange(1,i)
        raw[f'A{i}']=f'=A{a}+A{b}'
    e=Engine(raw)
    for _ in range(30):
        e.set('A1',str(random.randrange(1,100)))
        expected={}
        for c in raw:expected[c]=evaluate(e.ast[c],expected)
        assert e.values==expected
