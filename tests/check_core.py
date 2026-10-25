import ast,threading,time,subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
tree=ast.parse((Path(__file__).resolve().parents[1] / 'main.py').read_text(encoding='utf-8'))
saved=[]; launches=[]
ns=dict(AppState=object,threading=threading,subprocess=subprocess,
        get_service_status=lambda:'stopped',autostart_app_enabled=lambda:False,
        set_service_start_type=lambda value:True,save_config=lambda cfg:saved.append(dict(cfg)))
exec(compile(ast.Module([n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Api'],[]),'test','exec'),ns)
proc=SimpleNamespace(poll=lambda:None,wait=lambda timeout:0)
def launch(*args):
    time.sleep(.02); launches.append(args); return proc
ns.update(start_standalone=launch,stop_standalone=lambda p:None)
app=SimpleNamespace(process=None,config={},gf={},is_auto_testing=False,strategies=['a.bat'],push_status=lambda:None)
api=ns['Api'](app)
with ThreadPoolExecutor(max_workers=10) as pool:
    results=list(pool.map(lambda _:api.start_local('a.bat'),range(10)))
assert len(launches)==1 and sum(r['ok'] for r in results)==1
assert 'уже запущен' in results[-1]['error']
assert api.stop_local()['ok'] and app.process is None
ns['get_service_status']=lambda:'running'
assert 'Служба обхода' in api.start_local('a.bat')['error']
assert len(launches)==1
ns['get_service_status']=lambda:'stopped'
app.is_auto_testing=True
assert not api.start_local('a.bat')['ok']
app.is_auto_testing=False
assert not api.start_local('missing.bat')['ok']
# Failed sc config must not change disk or checkbox payload.
app.config={'autostart_service':True}; saved.clear()
ns['set_service_start_type']=lambda value:False
result=api.set_autostart('service',False)
assert not result['ok'] and result['autostart']['service'] and not saved
ns['set_service_start_type']=lambda value:True
result=api.set_autostart('service',False)
assert result['ok'] and not result['autostart']['service'] and saved[-1]['autostart_service'] is False
# If saving fails, undo the OS change and restore in-memory preference.
changes=[]
ns['set_service_start_type']=lambda value:changes.append(value) or True
def fail_save(cfg): raise PermissionError('locked')
ns['save_config']=fail_save
result=api.set_autostart('service',True)
assert not result['ok'] and result['autostart']['service'] is False and changes==[True,False]
# Real check function, with controlled HTTP responses and no network traffic.
class Response:
    def __init__(self,status): self.status_code=status
    def __enter__(self): return self
    def __exit__(self,*a): pass
request_error=type('RequestError',(Exception,),{})
requests=SimpleNamespace(exceptions=SimpleNamespace(RequestException=request_error))
ns['requests']=requests
exec(compile(ast.Module([n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='check_connection'],[]),'test','exec'),ns)
for status,expected in [(200,True),(204,True),(301,True),(403,False),(404,False),(429,False),(500,False),(503,False)]:
    requests.get=lambda *a,**kw:Response(status)
    assert ns['check_connection']('https://example.test') is expected
def fail_request(*a,**kw): raise request_error('timeout')
requests.get=fail_request
assert not ns['check_connection']('https://example.test')
print('PASS: 10 simultaneous manual launches create one process; service conflict; invalid strategy; stop; failed/successful autostart and rollback; HTTP statuses and timeout')
