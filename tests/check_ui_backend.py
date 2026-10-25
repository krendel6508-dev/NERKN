"""Проверки без UAC, сетевых соединений и изменения буфера пользователя."""
import ast
import ctypes
import json
import math
import os
import re
import threading
import time
from pathlib import Path
from types import SimpleNamespace

tree = ast.parse((Path(__file__).resolve().parents[1] / 'main.py').read_text(encoding='utf-8'))
terminated = []
process = SimpleNamespace(pid=12345, name=lambda:'TgWsProxy_windows.exe', create_time=lambda:10,
                          terminate=lambda:terminated.append(12345))
connections = [SimpleNamespace(pid=12345, status='LISTEN', laddr=SimpleNamespace(ip='127.0.0.1',port=1443))]
fake_psutil = SimpleNamespace(Error=RuntimeError, CONN_LISTEN='LISTEN',
    net_connections=lambda **kw:connections, Process=lambda pid:process,
    wait_procs=lambda processes,timeout:(processes,[]))
ns = dict(os=os, threading=threading, time=time, psutil=fake_psutil, json=json, math=math,
    AppState=object, LOOK_KEYS=('standard','modern','ios26'), SCHEME_KEYS=('classic','black','white'),
    CUSTOM_COLOR_KEYS=('bg','panel','term','text','border','accent','accent2','accent3','idle','testing'),
    _HEX6_RE=re.compile(r'#[0-9a-fA-F]{6}'), PROJECT_LINKS={'telegram':'https://t.me/nerknn','github':''},
    webbrowser=SimpleNamespace(open=lambda url: url == 'https://t.me/nerknn'))
nodes = [n for n in tree.body if (isinstance(n,ast.ClassDef) and n.name in ('Api','TgProxyManager'))
         or (isinstance(n,ast.FunctionDef) and n.name=='sanitize_custom')]
exec(compile(ast.Module(nodes,[]),'isolated','exec'),ns)
manager = ns['TgProxyManager']({})
manager.is_available=lambda:True
manager._port_listening=lambda:True
# A busy port must never cause an automatic process termination.
assert manager.start()[0] is False
token=manager.port_conflict['id']
assert terminated==[]
assert manager.resolve_port_conflict(token,False)[0]
assert terminated==[] and manager.port_conflict is None
# Consent is bound to this conflict, not a future listener.
manager._record_port_conflict(); token=manager.port_conflict['id']
process.create_time=lambda:11
assert not manager.resolve_port_conflict(token,True)[0] and not terminated
process.create_time=lambda:10
manager._record_port_conflict(); token=manager.port_conflict['id']
process.name=lambda:'unrelated.exe'
assert not manager.resolve_port_conflict(token,True)[0] and not terminated
# Known bridge, unchanged PID and creation time, explicit consent.
process.name=lambda:'TgWsProxy_windows.exe'
manager._record_port_conflict(); token=manager.port_conflict['id']
manager._port_listening=lambda:False
manager.start=lambda:(True,'')
assert manager.resolve_port_conflict(token,True)[0] and terminated==[12345]
assert not manager.resolve_port_conflict(token,True)[0]  # cannot reuse consent
copied=[]
ns['copy_text_to_clipboard']=copied.append
api=ns['Api'](SimpleNamespace(config={}))
theme={'base':'standard','scheme':'classic','c':dict.fromkeys(ns['CUSTOM_COLOR_KEYS'],'#123456'),
       'radius':7,'panelA':.42,'borderA':.27,'blur':18}
assert api.copy_theme(theme)['ok']
assert json.loads(copied[0])==ns['sanitize_custom'](theme)
assert not api.copy_theme({'c':{}})['ok']
assert api.open_project_link('telegram')['ok']
assert not api.open_project_link('github')['ok']
print('PASS: consent/cancel, changed owner, unknown owner, one-use token, current theme JSON, placeholder links')
