import sys, os, time, json, base64, socket, subprocess, tempfile
from pathlib import Path
from websockets.sync.client import connect

ROOT=Path(sys.argv[1]).resolve()
OUT=ROOT / 'evidencias'; OUT.mkdir(exist_ok=True)
def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0)); return s.getsockname()[1]
sp,bp=port(),port()
profile=Path(tempfile.mkdtemp(prefix='lab10-firefox-'))
(profile/'user.js').write_text('user_pref("browser.shell.checkDefaultBrowser", false);\nuser_pref("browser.startup.homepage_override.mstone", "ignore");\nuser_pref("datareporting.policy.dataSubmissionEnabled", false);\n')
log=[]
def record(name,**kw):
    x={'test':name,**kw};log.append(x);print(json.dumps(x,ensure_ascii=False),flush=True)
serverlog=open(OUT/'server.log','w'); browserlog=open(OUT/'firefox.log','w')
server=subprocess.Popen([sys.executable,'-B','-m','streamlit','run',str(ROOT/'app.py'),'--server.headless=true','--server.address=127.0.0.1',f'--server.port={sp}','--browser.gatherUsageStats=false','--server.fileWatcherType=none'],cwd=ROOT,stdout=serverlog,stderr=subprocess.STDOUT)
browser=None
try:
    browser=subprocess.Popen(['firefox','--headless','--no-remote','--profile',str(profile),'--remote-debugging-port',str(bp),'about:blank'],stdout=browserlog,stderr=subprocess.STDOUT)
    ws=None
    for _ in range(100):
        try: ws=connect(f'ws://127.0.0.1:{bp}/session',open_timeout=1,legacy=True);break
        except Exception:time.sleep(.2)
    if ws is None:raise RuntimeError('Firefox BiDi did not start')
    count=0
    def cmd(method,params):
        global count
        count+=1;ident=count
        ws.send(json.dumps({'id':ident,'method':method,'params':params}))
        while True:
            r=json.loads(ws.recv(timeout=30))
            if r.get('id')==ident:
                if r.get('type')=='error':raise RuntimeError(json.dumps(r))
                return r.get('result',{})
    record('B00_session',result=cmd('session.new',{'capabilities':{'alwaysMatch':{'browserName':'firefox'}}}))
    ctx=cmd('browsingContext.create',{'type':'tab'})['context']
    def evaluate(expression):
        r=cmd('script.evaluate',{'expression':f'JSON.stringify({expression})','target':{'context':ctx},'awaitPromise':True})
        if r.get('type')=='exception':raise RuntimeError(str(r))
        return json.loads(r['result']['value'])
    def wait_for(expression,seconds=15):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            r=evaluate(expression)
            if r:return r
            time.sleep(.25)
        return None
    def screenshot(name):
        r=cmd('browsingContext.captureScreenshot',{'context':ctx,'origin':'viewport','format':{'type':'image/png'}})
        (OUT/name).write_bytes(base64.b64decode(r['data']))
    def tab(label):
        evaluate('(()=>{const t=[...document.querySelectorAll("[role=tab]")].find(x=>x.innerText==='+json.dumps(label)+');t.click();return true})()')
        time.sleep(.7)
    def pointer(x,y):
        cmd('input.performActions',{'context':ctx,'actions':[{'type':'pointer','id':'mouse','parameters':{'pointerType':'mouse'},'actions':[{'type':'pointerMove','x':int(x),'y':int(y),'origin':'viewport'},{'type':'pointerDown','button':0},{'type':'pointerUp','button':0}]}]})
    cmd('browsingContext.setViewport',{'context':ctx,'viewport':{'width':1440,'height':1000},'devicePixelRatio':1})
    cmd('browsingContext.navigate',{'context':ctx,'url':f'http://127.0.0.1:{sp}','wait':'complete'})
    ready=wait_for('document.querySelectorAll(".js-plotly-plot").length>=9',30)
    wait_for('getComputedStyle(document.querySelector(".top-banner")).position==="relative"')
    time.sleep(.7)
    record('B01_start',ready=ready,charts=evaluate('document.querySelectorAll(".js-plotly-plot").length'),text=evaluate('document.body.innerText').strip()[:300])
    screenshot('desktop_resumen.png')
    zoom=evaluate("""(()=>{const g=[...document.querySelectorAll('.js-plotly-plot')].find(g=>g.data?.[0]?.type==='scatter' && g.getBoundingClientRect().width>0);const before=JSON.stringify(g.layout.xaxis.range);g.querySelector('[data-title=\"Zoom in\"]')?.click();return {before,after:JSON.stringify(g.layout.xaxis.range)}})()""")
    record('B01a_history_zoom',changed=zoom['before']!=zoom['after'])
    def chart_point(kind, text=None):
        expression = """(()=>{const g=[...document.querySelectorAll('.js-plotly-plot')].find(g=>COND);g.scrollIntoView({block:'center'});const nodes=[...g.querySelectorAll(SELECTOR)];const e=TEXT?nodes.find(e=>e.textContent===TEXT):nodes.at(-1);const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()"""
        cond, selector = {
            'region': ("g.data?.[0]?.orientation==='h' && g.data[0].y.includes('Asia')", ".barlayer .point path"),
            'country': ("g.data?.[0]?.orientation==='h' && g.data[0].y.includes('El Salvador')", ".barlayer .point path"),
            'tree': ("g.data?.[0]?.type==='treemap'", ".slicetext"),
        }[kind]
        expression=expression.replace('.at(-1)', '.at(-2)' if kind == 'country' else '.at(-1)').replace('COND',cond).replace('SELECTOR',json.dumps(selector)).replace('TEXT',json.dumps(text))
        return evaluate(expression)
    rp=evaluate("""(()=>{const g=[...document.querySelectorAll('.js-plotly-plot')].find(g=>g.data?.[0]?.orientation==='h' && g.data[0].y.includes('Asia'));g.scrollIntoView({block:'center'});const p=[...g.querySelectorAll('.barlayer .point path')][g.data[0].y.indexOf('Asia')];const r=p.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()""")
    pointer(rp['x'],rp['y'])
    record('B02_region_click',updated=wait_for("[...document.querySelectorAll('.js-plotly-plot')].some(g=>g.data?.[0]?.type==='box' && g.layout.xaxis.title.text.includes('Asia'))"))
    tab('Explorar datos')
    point=chart_point('country');pointer(point['x'],point['y'])
    record('B03_country_click',updated=wait_for("document.body.innerText.includes('Evolución: Estados Unidos de América')"))
    screenshot('desktop_explorar_despues.png')
    zoom=evaluate("""(()=>{const g=[...document.querySelectorAll('.js-plotly-plot')].find(g=>g.data?.[0]?.type==='scatter' && g.getBoundingClientRect().width>0);const before=JSON.stringify(g.layout.xaxis.range);g.querySelector('[data-title=\"Zoom in\"]')?.click();return {before,after:JSON.stringify(g.layout.xaxis.range)}})()""")
    record('B03a_country_zoom',changed=zoom['before']!=zoom['after'])
    blank=evaluate("""(()=>{const g=[...document.querySelectorAll('.js-plotly-plot')].find(g=>g.data?.[0]?.orientation==='h' && g.data[0].y.includes('El Salvador'));g.scrollIntoView({block:'center'});const r=g.querySelector('.nsewdrag').getBoundingClientRect();return {x:r.x+r.width-8,y:r.y+r.height-3}})()""")
    pointer(blank['x'],blank['y']);pointer(blank['x'],blank['y'])
    record('B04_country_clear',cleared=wait_for("!document.body.innerText.includes('Evolución:')"))
    tree=chart_point('tree','Terrestre');pointer(tree['x'],tree['y']);time.sleep(.6)
    record('B05_tree_down',level=evaluate("[...document.querySelectorAll('.js-plotly-plot')].find(g=>g.data?.[0]?.type==='treemap').data[0].level"))
    back=evaluate("""(()=>{const g=[...document.querySelectorAll('.js-plotly-plot')].find(g=>g.data?.[0]?.type==='treemap');const es=[...g.querySelectorAll('.pathbar text')];const e=es.find(e=>e.textContent.includes('Todas las vías'))??es[0];if(!e)return {html:g.querySelector('.treemaplayer')?.innerHTML.slice(0,300)};const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2,text:e.textContent}})()""")
    evaluate("(()=>{[...document.querySelectorAll('button')].find(b=>b.innerText==='Volver a todas las vías').click();return true})()");time.sleep(.8)
    record('B06_tree_up',button=back,level=evaluate("[...document.querySelectorAll('.js-plotly-plot')].find(g=>g.data?.[0]?.type==='treemap').data[0].level??''"))
    heat=evaluate("""(()=>{const g=[...document.querySelectorAll('.js-plotly-plot')].find(g=>g.data?.[0]?.type==='heatmap');g.scrollIntoView({block:'center'});const r=g.querySelector('.nsewdrag').getBoundingClientRect();return {x:r.x+r.width/4,y:r.y+r.height/2}})()""")
    cmd('input.performActions',{'context':ctx,'actions':[{'type':'pointer','id':'mouse','parameters':{'pointerType':'mouse'},'actions':[{'type':'pointerMove','x':int(heat['x']),'y':int(heat['y']),'origin':'viewport'}]}]})
    time.sleep(.3)
    record('B07_heatmap_hover',tooltip=evaluate("[...document.querySelectorAll('.hoverlayer')].map(e=>e.textContent).filter(Boolean)"))
    tab('Modelos');screenshot('desktop_modelos.png')
    legend=evaluate("""(()=>{const g=[...document.querySelectorAll('.js-plotly-plot')].find(g=>g.data?.[0]?.name==='Observado' && g.data.length>2);g.scrollIntoView({block:'center'});const e=g.querySelector('.legendtoggle');const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()""")
    pointer(legend['x'],legend['y']);time.sleep(.3)
    record('B08a_models_legend',visibilities=evaluate("[...document.querySelectorAll('.js-plotly-plot')].find(g=>g.data?.[0]?.name==='Observado' && g.data.length>2).data.map(t=>t.visible??true)"))
    err=evaluate("""(()=>{const g=[...document.querySelectorAll('.js-plotly-plot')].find(g=>g.data?.[0]?.type==='bar' && g.layout.xaxis.title.text.includes('viajeros/mes'));g.scrollIntoView({block:'center'});const r=g.querySelector('.barlayer .point path').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()""")
    cmd('input.performActions',{'context':ctx,'actions':[{'type':'pointer','id':'mouse','parameters':{'pointerType':'mouse'},'actions':[{'type':'pointerMove','x':int(err['x']),'y':int(err['y']),'origin':'viewport'}]}]})
    time.sleep(.3)
    record('B08b_error_hover',tooltip=evaluate("[...document.querySelectorAll('.hoverlayer')].map(e=>e.textContent).filter(Boolean)"))
    record('B08_models',visible=evaluate("document.body.innerText.includes('Desempeño por modelo')"),errors=evaluate("[...document.querySelectorAll('[data-testid=stException]')].map(e=>e.innerText)"))
    tab('Acerca de');screenshot('desktop_acerca.png')
    tab('Resumen')
    cmd('browsingContext.setViewport',{'context':ctx,'viewport':{'width':390,'height':844},'devicePixelRatio':1})
    time.sleep(.5)
    close=evaluate("""(()=>{const side=document.querySelector('[data-testid=stSidebar]');return [...side.querySelectorAll('button')].map(e=>({label:e.getAttribute('aria-label'),testid:e.getAttribute('data-testid'),html:e.outerHTML.slice(0,250)}))})()""")
    evaluate("""(()=>{const b=document.querySelector('[data-testid=stSidebarCollapseButton] button')??document.querySelector('[data-testid=stSidebarCollapseButton]');if(b)b.click();return !!b})()""")
    time.sleep(.8)
    screenshot('mobile_resumen.png')
    record('B09_mobile',buttons=close,layout=evaluate("""(()=>{const r=s=>{const e=document.querySelector(s);if(!e)return null;const b=e.getBoundingClientRect();return {x:b.x,y:b.y,width:b.width,height:b.height}};return {viewport:innerWidth,bodyWidth:document.body.scrollWidth,sidebar:r('[data-testid=stSidebar]'),banner:r('.top-banner'),title:r('.banner-titles h1'),main:r('[data-testid=stMainBlockContainer]')}})()"""))
except Exception as exc:
    record('B_ERROR',error=str(exc))
finally:
    (OUT/'browser_results.json').write_text(json.dumps(log,ensure_ascii=False,indent=2))
    if browser:
        browser.terminate()
        try:browser.wait(timeout=5)
        except subprocess.TimeoutExpired:browser.kill()
    server.terminate()
    try:server.wait(timeout=5)
    except subprocess.TimeoutExpired:server.kill()
    serverlog.close();browserlog.close()
