"""Local visual editor for the vsk3000 GitHub Pages guides."""
from pathlib import Path
import argparse, base64, hashlib, json, mimetypes, os, re, secrets, subprocess, sys
import threading, time, uuid, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, unquote
from urllib.request import Request, urlopen
from urllib.error import HTTPError

RESOURCE = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.tools'))
from bs4 import BeautifulSoup

PAGES = {'index.html': 'Xiaomi 4C/4A', 'ax3000t.html': 'Xiaomi AX3000T'}
REPO = 'vsk3000/vsk3000'
SITE = 'https://vsk3000.github.io/vsk3000/'
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_bytes(data if isinstance(data, bytes) else data.encode('utf-8'))
    os.replace(tmp, path)

def blob_sha(data):
    if isinstance(data, str): data = data.encode('utf-8')
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()

def safe_url(value, image=False):
    value = value.strip()
    if any(ord(c) < 32 for c in value) or '\\' in value: return False
    parts = urlsplit(value)
    if image: return bool(re.fullmatch(r'assets/[\w./-]+', value)) and '..' not in value
    return parts.scheme.lower() in ('http', 'https', 'mailto', 'tel') or (not parts.scheme and not value.startswith('//'))

def clean_html(html):
    doc = BeautifulSoup(html, 'html.parser')
    for node in doc.select('script,style,iframe,object,embed,form,input,textarea,select,link,meta,base,svg,math'):
        node.decompose()
    allowed = {'p','div','span','strong','b','em','i','u','s','br','h2','h3','h4','ul','ol','li','a','img','figure','figcaption','blockquote','pre','code','details','summary','small','button','table','thead','tbody','tr','td','th','hr','mark'}
    attrs = {'class','id','href','src','alt','title','width','height','loading','decoding','target','rel','type','start','colspan','rowspan','open','aria-label','aria-hidden','data-lightbox'}
    for node in list(doc.find_all(True)):
        if node.name not in allowed:
            node.unwrap(); continue
        for attr in list(node.attrs):
            if attr not in attrs: del node[attr]
        if node.has_attr('href') and not safe_url(node['href']): del node['href']
        if node.has_attr('src') and not safe_url(node['src'], True): node.decompose(); continue
        if node.name == 'a' and str(node.get('href','')).startswith(('http:', 'https:')):
            node['target'] = '_blank'; node['rel'] = 'noopener noreferrer'
        if node.name == 'button': node['type'] = 'button'
    return str(doc)

def parse_page(html, page):
    doc = BeautifulSoup(html, 'html.parser')
    items = []
    for section in doc.select('.guide-section'):
        sid = section['data-section']
        heading = section.find(['h1','h2'])
        title = heading.get_text() if heading else sid
        nav = doc.select_one(f'a.nav-link[href="#{sid}"]')
        nav_title = nav.select('span')[-1].get_text() if nav else title
        kicker_node=section.select_one('.section-kicker')
        kicker_text=kicker_node.get_text() if kicker_node else ''
        for element in section.select('.section-kicker'): element.decompose()
        if heading: heading.decompose()
        items.append({'id': sid, 'title': title, 'nav': nav_title, 'kicker':kicker_text, 'html': section.decode_contents()})
    contacts = doc.select_one('#contacts')
    theme=doc.select_one('#editor-theme')
    color=re.search(r'--blue:(#[0-9a-fA-F]{6})',theme.get_text()) if theme else None
    return {'page': page, 'sections': items, 'contacts': contacts.decode_contents() if contacts else '', 'color': color.group(1) if color else '#2467d5'}

def render_page(base, model):
    doc = BeautifulSoup(base, 'html.parser')
    sections = model.get('sections', [])
    if not 1 <= len(sections) <= 80: raise ValueError('Оставьте хотя бы один раздел (максимум 80).')
    ids = [s['id'] for s in sections]
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r'[a-zA-Z][\w.-]*', x) for x in ids):
        raise ValueError('Повторяющиеся или недопустимые названия разделов.')
    main = doc.select_one('main')
    for s in doc.select('.guide-section'): s.decompose()
    nav = doc.select_one('.sidebar nav')
    for a in nav.select('.nav-link'):
        if a.get('href') != '#contacts': a.decompose()
    contacts = doc.select_one('#contacts')
    for i, item in enumerate(sections):
        section = doc.new_tag('section', attrs={'class':'guide-section','data-section':item['id'],'aria-labelledby':item['id']})
        kicker = doc.new_tag('div', attrs={'class':'section-kicker'})
        kicker.string = item.get('kicker') or ('РУКОВОДСТВО ПОЛЬЗОВАТЕЛЯ' if i == 0 else f'РАЗДЕЛ {i:02}')
        section.append(kicker)
        heading = doc.new_tag('h1' if i == 0 else 'h2', id=item['id'])
        heading.string = item['title'].strip() or 'Новый раздел'
        section.append(heading)
        fragment = BeautifulSoup(clean_html(item['html']), 'html.parser')
        for child in list(fragment.contents): section.append(child)
        contacts.insert_before(section)
        link = doc.new_tag('a', href='#'+item['id'], attrs={'class':'nav-link'})
        num = doc.new_tag('span', attrs={'class':'nav-number'}); num.string=f'{i:02}'; link.append(num)
        name = doc.new_tag('span'); name.string=item.get('nav','').strip() or heading.string; link.append(name)
        last = nav.select_one('a[href="#contacts"]')
        if last: last.insert_before(link)
        else: nav.append(link)
    contacts.clear()
    frag = BeautifulSoup(clean_html(model.get('contacts','')), 'html.parser')
    for child in list(frag.contents): contacts.append(child)
    doc.select_one('.brand')['href'] = '#'+ids[0]
    color = model.get('color', '#2467d5')
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', color): raise ValueError('Некорректный цвет.')
    theme = doc.select_one('#editor-theme')
    if theme: theme.decompose()
    theme = doc.new_tag('style', id='editor-theme'); theme.string=':root{--blue:'+color+'}'
    doc.head.append(theme)
    # Publishing refuses broken anchors, so deleted sections cannot leave silent dead links.
    all_ids = [x['id'] for x in doc.select('[id]')]
    if len(all_ids) != len(set(all_ids)): raise ValueError('На странице есть повторяющиеся заголовки. Удалите скопированный блок и вставьте его как текст.')
    return str(doc)

class Editor:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.data = self.root / '.site-editor'
        self.data.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.token = None
        self.status = {'busy':False,'stage':'idle','message':'Изменения пока не опубликованы из приложения.'}
        self.last_seen = time.monotonic()
        self.bases = {p:(self.root/p).read_text(encoding='utf-8') for p in PAGES}
        self.baseline = json.loads((self.data/'baseline.json').read_text()) if (self.data/'baseline.json').exists() else {}
        self.models = {}
        self.last_snapshot = {}
        for p in PAGES:
            path = self.data / (p+'.json')
            self.models[p] = json.loads(path.read_text(encoding='utf-8')) if path.exists() else parse_page(self.bases[p],p)
            original_sections={s['id']:s for s in parse_page(self.bases[p],p)['sections']}
            for s in self.models[p]['sections']:
                s.setdefault('kicker',original_sections.get(s['id'],{}).get('kicker',''))
            if not path.exists():
                atomic(self.data/'history'/f'{time.time_ns()}-{p}.json',json.dumps(self.models[p],ensure_ascii=False))

    def git(self, *args, input=None, env=None, timeout=60):
        result = subprocess.run(['git',*args],cwd=self.root,input=input,text=True,encoding='utf-8',capture_output=True,creationflags=FLAGS,env=env,timeout=timeout)
        if result.returncode: raise RuntimeError('Git: '+(result.stderr.strip() or 'команда не выполнена')[:700])
        return result.stdout.strip()

    def api(self, path, method='GET', data=None):
        headers = {'Accept':'application/vnd.github+json','User-Agent':'Router-Site-Editor','X-GitHub-Api-Version':'2022-11-28'}
        if self.token: headers['Authorization']='Bearer '+self.token
        body = json.dumps(data).encode() if data is not None else None
        if body: headers['Content-Type']='application/json'
        try:
            with urlopen(Request('https://api.github.com/'+path, data=body, headers=headers, method=method),timeout=45) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code in (401,403): raise RuntimeError('Нет доступа к GitHub. Нажмите «Подключить GitHub» и войдите в аккаунт vsk3000.') from None
            if exc.code in (409,422): raise RuntimeError('Сайт изменился на GitHub. Черновик сохранён. Загрузите свежую версию перед публикацией.') from None
            raise RuntimeError(f'GitHub вернул ошибку {exc.code}. Черновик сохранён; повторите позже.') from None

    def authenticate(self, interactive=True):
        self.status.update(busy=True,stage='auth',message='Войдите в GitHub в открывшемся окне браузера…')
        env = os.environ.copy()
        env['GIT_TERMINAL_PROMPT']='0'
        env['GCM_INTERACTIVE']='always' if interactive else 'never'
        try:
            result = self.git('-c','credential.interactive='+('true' if interactive else 'false'),'credential','fill',input='protocol=https\nhost=github.com\nusername=vsk3000\n\n',env=env,timeout=240)
            fields = dict(line.split('=',1) for line in result.splitlines() if '=' in line)
            self.token = fields.get('password')
            if not self.token: raise RuntimeError('GitHub не подключён.')
            repo = self.api('repos/'+REPO)
            if not repo.get('permissions',{}).get('push'): raise RuntimeError('У этого аккаунта нет права изменять репозиторий vsk3000/vsk3000.')
            self.status.update(busy=False,stage='ready',message='GitHub подключён. Можно публиковать сайт.')
        except Exception:
            self.token=None
            self.status.update(busy=False,stage='error',message='Не удалось подключить GitHub. Повторите вход через кнопку «Подключить GitHub».')

    def snapshot(self):
        return {'pages':PAGES,'models':self.models,'connected':bool(self.token),'status':self.status,'site':SITE,'root':str(self.root),'history':self.history()}

    def save(self, model):
        page=model.get('page')
        if page not in PAGES: raise ValueError('Неизвестная страница.')
        rendered=render_page(self.bases[page],model)
        with self.lock:
            path=self.data/(page+'.json')
            if path.exists() and time.time()-self.last_snapshot.get(page,0)>60:
                atomic(self.data/'history'/f'{time.time_ns()}-{page}.json',path.read_bytes())
                self.last_snapshot[page]=time.time()
            # Always retain a rolling snapshot of the last saved session before publication.
            atomic(path,json.dumps(model,ensure_ascii=False))
            atomic(self.data/'preview'/page,rendered)
            self.models[page]=model
        return {'saved':True,'time':time.strftime('%H:%M:%S')}

    def history(self):
        return [{'id':p.name,'page':'ax3000t.html' if 'ax3000t' in p.name else 'index.html','time':time.strftime('%d.%m.%Y %H:%M',time.localtime(p.stat().st_mtime))} for p in sorted((self.data/'history').glob('*.json'),reverse=True)[:30]]

    def restore(self, name):
        if Path(name).name!=name: raise ValueError('Некорректный файл.')
        model=json.loads((self.data/'history'/name).read_text(encoding='utf-8'))
        page=model['page']
        atomic(self.data/'history'/f'{time.time_ns()}-{page}.json',json.dumps(self.models[page],ensure_ascii=False))
        self.save(model)
        return model

    def upload(self, name, encoded):
        raw=base64.b64decode(encoded,validate=True)
        if len(raw)>12*1024*1024: raise ValueError('Изображение больше 12 МБ.')
        ext=Path(name).suffix.lower()
        valid=(ext=='.png' and raw.startswith(b'\x89PNG\r\n')) or (ext in ('.jpg','.jpeg') and raw.startswith(b'\xff\xd8\xff')) or (ext=='.gif' and raw.startswith(b'GIF8')) or (ext=='.webp' and raw[:4]==b'RIFF' and raw[8:12]==b'WEBP')
        if not valid: raise ValueError('Выберите изображение PNG, JPG, GIF или WebP.')
        path='assets/uploads/'+uuid.uuid4().hex+ext
        atomic(self.root/path,raw)
        return {'path':path}

    def launch_publish(self):
        with self.lock:
            if self.status['busy']: raise ValueError('Дождитесь завершения текущей операции.')
            if not self.token: raise ValueError('Сначала подключите GitHub.')
            models=json.loads(json.dumps(self.models))
            self.status.update(busy=True,stage='publishing',message='Проверяю изменения и отправляю сайт на GitHub…')
            threading.Thread(target=self.publish,args=(models,),daemon=True).start()

    def publish(self, models):
        try:
            prefix='repos/'+REPO
            head=self.api(prefix+'/git/ref/heads/master')['object']['sha']
            commit=self.api(prefix+'/git/commits/'+head)
            tree=self.api(prefix+'/git/trees/'+commit['tree']['sha']+'?recursive=1')
            remote={x['path']:x['sha'] for x in tree['tree'] if x['type']=='blob'}
            files={}
            for page,model in models.items():
                html=render_page(self.bases[page],model)
                ids={x['id'] for x in BeautifulSoup(html,'html.parser').select('[id]')}
                broken=[a['href'] for a in BeautifulSoup(html,'html.parser').select('a[href^="#"]') if a['href'][1:] not in ids]
                if broken: raise ValueError('Есть ссылки на удалённые разделы: '+', '.join(sorted(set(broken)))+'. Исправьте их перед публикацией.')
                # The saved baseline guards against overwriting edits made elsewhere.
                baseline=self.baseline.get(page,blob_sha(self.bases[page]))
                if remote.get(page)!=baseline:
                    raise ValueError('На GitHub появилась новая версия '+PAGES[page]+'. Ваш черновик сохранён. Нажмите «Загрузить с сайта» и перенесите нужные правки из истории.')
                files[page]=html
                files['site-content/'+page]=html
                for image in BeautifulSoup(html,'html.parser').select('img[src^="assets/uploads/"]'):
                    path=image['src']
                    if path not in remote:
                        raw=(self.root/path).read_bytes()
                        blob=self.api(prefix+'/git/blobs','POST',{'content':base64.b64encode(raw).decode(),'encoding':'base64'})
                        files[path]={'sha':blob['sha']}
            entries=[]
            for path,content in files.items():
                if isinstance(content,str) and remote.get(path)==blob_sha(content): continue
                entry={'path':path,'mode':'100644','type':'blob'}
                entry.update({'content':content} if isinstance(content,str) else content)
                entries.append(entry)
            if not entries:
                self.status.update(busy=False,stage='success',message='На сайте уже актуальная версия.'); return
            newtree=self.api(prefix+'/git/trees','POST',{'base_tree':commit['tree']['sha'],'tree':entries})['sha']
            newcommit=self.api(prefix+'/git/commits','POST',{'message':'Update guides in visual site editor','tree':newtree,'parents':[head]})['sha']
            self.api(prefix+'/git/refs/heads/master','PATCH',{'sha':newcommit,'force':False})
            with self.lock:
                for page in PAGES:
                    atomic(self.data/'history'/f'{time.time_ns()}-{page}.json',json.dumps(models[page],ensure_ascii=False))
                    atomic(self.root/page,files[page]); atomic(self.root/'site-content'/page,files[page])
                    self.bases[page]=files[page]; self.baseline[page]=blob_sha(files[page])
                atomic(self.data/'baseline.json',json.dumps(self.baseline))
            self.status.update(stage='deploying',message='Файлы отправлены. GitHub Pages обновляет сайт…',commit=newcommit)
            # Check the actual public files, rather than reporting a push as a deployment.
            for attempt in range(36):
                time.sleep(5)
                matches=True
                for page in PAGES:
                    try:
                        req=Request(SITE+page+'?editor='+newcommit,headers={'Cache-Control':'no-cache'})
                        with urlopen(req,timeout=15) as response: live=response.read().decode('utf-8').replace('\r\n','\n')
                        if live!=files[page].replace('\r\n','\n'): matches=False
                    except Exception: matches=False
                if matches:
                    self.status.update(busy=False,stage='success',message='Опубликовано! Новая версия уже доступна на сайте.'); return
            self.status.update(busy=False,stage='pending',message='Файлы сохранены на GitHub. Публикация ещё идёт; проверьте сайт через несколько минут.')
        except Exception as exc:
            message=str(exc) if isinstance(exc,(ValueError,RuntimeError)) else 'Не удалось завершить публикацию. Черновик сохранён; проверьте интернет и повторите.'
            self.status.update(busy=False,stage='error',message=message)

    def refresh(self):
        if self.status['busy']: raise ValueError('Дождитесь завершения публикации.')
        fetched={}
        for page in PAGES:
            item=self.api('repos/'+REPO+'/contents/'+page+'?ref=master')
            fetched[page]=base64.b64decode(item['content']).decode('utf-8')
        with self.lock:
            for page,html in fetched.items():
                atomic(self.data/'history'/f'{time.time_ns()}-{page}.json',json.dumps(self.models[page],ensure_ascii=False))
                self.bases[page]=html; self.baseline[page]=blob_sha(html)
                atomic(self.root/page,html)
                atomic(self.root/'site-content'/page,html)
                self.save(parse_page(html,page))
            atomic(self.data/'baseline.json',json.dumps(self.baseline))
        return self.snapshot()

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def reply(self,data,status=200,mime='application/json; charset=utf-8'):
        if not isinstance(data,bytes): data=json.dumps(data,ensure_ascii=False).encode('utf-8')
        self.send_response(status); self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(data))); self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(data)
    def authorized(self):
        return self.headers.get('X-Editor-Token')==self.server.secret and self.headers.get('Host')==self.server.host
    def do_GET(self):
        path=unquote(urlsplit(self.path).path)
        if self.headers.get('Host')!=self.server.host: return self.reply({'error':'Forbidden'},403)
        if path.startswith('/api/'):
            if not self.authorized(): return self.reply({'error':'Forbidden'},403)
            self.server.editor.last_seen=time.monotonic()
            return self.reply(self.server.editor.snapshot())
        if path in ('/','/editor.js','/editor.css'):
            file=RESOURCE/'ui'/({'/':'index.html','/editor.js':'editor.js','/editor.css':'editor.css'}[path])
        elif path.startswith('/preview/'):
            rel=path[len('/preview/'):]
            if rel in PAGES:
                model=self.server.editor.models[rel]
                data=render_page(self.server.editor.bases[rel],model).encode('utf-8')
                return self.reply(data,mime='text/html; charset=utf-8')
            if not rel.startswith('assets/'): return self.reply({'error':'Not found'},404)
            file=(self.server.editor.root/rel).resolve()
            if not file.is_relative_to(self.server.editor.root/'assets'): return self.reply({'error':'Forbidden'},403)
        else: return self.reply({'error':'Not found'},404)
        if not file.is_file(): return self.reply({'error':'Not found'},404)
        mime=mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
        self.reply(file.read_bytes(),mime=mime+('; charset=utf-8' if mime.startswith('text/') else ''))
    def do_POST(self):
        if not self.authorized(): return self.reply({'error':'Forbidden'},403)
        origin=self.headers.get('Origin')
        if origin and origin!='http://'+self.server.host: return self.reply({'error':'Forbidden'},403)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<20*1024*1024: raise ValueError('Слишком большой запрос.')
            payload=json.loads(self.rfile.read(size))
            editor=self.server.editor; path=urlsplit(self.path).path
            if path=='/api/save': result=editor.save(payload)
            elif path=='/api/upload': result=editor.upload(payload['name'],payload['data'])
            elif path=='/api/publish': editor.launch_publish(); result={'started':True}
            elif path=='/api/auth':
                if editor.status['busy']: raise ValueError('Дождитесь текущей операции.')
                threading.Thread(target=editor.authenticate,daemon=True).start(); result={'started':True}
            elif path=='/api/restore': result=editor.restore(payload['id'])
            elif path=='/api/refresh': result=editor.refresh()
            elif path=='/api/quit': threading.Thread(target=self.server.shutdown,daemon=True).start(); result={'closed':True}
            else: raise ValueError('Неизвестная операция.')
            self.reply(result)
        except Exception as exc:
            self.reply({'error':str(exc) if isinstance(exc,(ValueError,RuntimeError)) else 'Не удалось сохранить изменения. Попробуйте ещё раз.'},400)

def open_window(url, data):
    edge=Path(os.environ.get('PROGRAMFILES(X86)','C:/Program Files (x86)'))/'Microsoft/Edge/Application/msedge.exe'
    if edge.exists():
        subprocess.Popen([str(edge),'--app='+url,'--user-data-dir='+str(data/'browser'),'--no-first-run'],creationflags=FLAGS)
    else: webbrowser.open(url)

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--root'); parser.add_argument('--no-browser',action='store_true'); parser.add_argument('--port',type=int,default=0)
    args=parser.parse_args()
    default=Path(sys.executable).parent.parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]
    root=Path(args.root) if args.root else default
    existing=root/'.site-editor/session.json'
    if existing.exists() and not args.no_browser:
        try:
            previous=json.loads(existing.read_text())['url']
            parts=urlsplit(previous)
            if parts.hostname=='127.0.0.1' and parts.port:
                with urlopen(Request('http://'+parts.netloc+'/api/state',headers={'X-Editor-Token':parts.fragment}),timeout=2) as response:
                    if response.status==200:
                        open_window(previous,root/'.site-editor'); return
        except Exception: pass
    editor=Editor(root)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    server.secret=secrets.token_urlsafe(32); server.editor=editor
    server.host='127.0.0.1:'+str(server.server_port)
    url='http://'+server.host+'/#'+server.secret
    # Keep the local launch URL private; it never goes into the repository or public page.
    atomic(editor.data/'session.json',json.dumps({'url':url,'pid':os.getpid()}))
    if not args.no_browser:
        open_window(url,editor.data)
    def watchdog():
        while True:
            time.sleep(15)
            if time.monotonic()-editor.last_seen>150 and not editor.status['busy']:
                server.shutdown(); return
    threading.Thread(target=watchdog,daemon=True).start()
    server.serve_forever()
    server.server_close()

if __name__=='__main__':
    try: main()
    except Exception as exc:
        if not getattr(sys,'frozen',False): raise
        import tkinter.messagebox
        tkinter.messagebox.showerror('Редактор сайта','Не удалось открыть редактор.\n'+str(exc))
