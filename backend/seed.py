def seed():
    cells={}
    for i,c in enumerate('BCDEFG'):
        prev=chr(ord(c)-1)
        cells[c+'2']='120' if i==0 else f'={prev}2*(1+{c}3)'
        cells[c+'3']='0.08'; cells[c+'4']='240'; cells[c+'5']=f'={c}2*{c}4'
        cells[c+'7']='0.22'; cells[c+'8']=f'={c}5*{c}7'; cells[c+'9']=f'={c}5-{c}8'
        cells[c+'11']='12500'; cells[c+'12']='4500'; cells[c+'13']='2800'
        cells[c+'14']=f'=SUM({c}11:{c}13)'; cells[c+'16']=f'={c}9-{c}14'; cells[c+'17']=f'={c}16/{c}5'
        cells[c+'19']='180000' if i==0 else f'={prev}20'
        cells[c+'20']=f'={c}19+{c}16'
    return cells
