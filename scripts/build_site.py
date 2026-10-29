"""Rebuild the static guide from the original Google Docs HTML export."""
from pathlib import Path
from html import escape
from urllib.parse import urlparse, parse_qs, unquote
import base64, re, sys, struct, json
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.tools'))
from bs4 import BeautifulSoup, NavigableString

source = BeautifulSoup((ROOT/'source-materials/google-document.html').read_text(encoding='utf-8'), 'html.parser')
nodes = list(source.body.find_all(recursive=False))
sections = [
 ('start','Начало работы',0,4),
 ('connection','Подключение роутера',4,8),
 ('restore','Восстановление после сброса',8,18),
 ('web-panel','Веб-панель управления',18,26),
 ('reset','Сброс настроек',26,40),
 ('troubleshooting','Если роутер не работает',40,44),
 ('main-router','Роутер как основной',44,82),
 ('wifi','Название и пароль Wi-Fi',82,103)
]
styles = dict(re.findall(r'\.([\w-]+)\{([^}]+)\}',source.style.string))
id_map = {nodes[start].get('id'):sid for sid,_,start,_ in sections}
images=[]
(ROOT/'assets/images').mkdir(parents=True,exist_ok=True)

def text(node):
    return node.get_text('',strip=False).replace('\u200b','').strip()

def serialize(node, top_heading=False):
    if isinstance(node,NavigableString): return escape(str(node).replace('\u200b',''))
    name=node.name
    if name in ('script','style'):return ''
    if name=='br':return '<br>'
    if name=='img':
        data=base64.b64decode(node['src'].split(',',1)[1])
        number=len(images)+1
        filename=f'assets/images/step-{number:02}.png'
        (ROOT/filename).write_bytes(data)
        width,height=struct.unpack('>II',data[16:24])
        caption=node.find_parent(['p','h1','li'])
        label=text(caption) if caption else ''
        if not label or len(label)>150:label=f'Иллюстрация к инструкции, шаг {number}'
        images.append(filename)
        return f'<a class="screenshot" href="{filename}" data-lightbox aria-label="Увеличить: {escape(label,quote=True)}"><img src="{filename}" width="{width}" height="{height}" alt="{escape(label,quote=True)}" loading="lazy" decoding="async"></a>'
    content=''.join(serialize(child) for child in node.children)
    if name=='span':
        rule=';'.join(styles.get(c,'') for c in node.get('class',[]))
        if 'font-weight:700' in rule:return '<strong>'+content+'</strong>'
        return content
    if name=='a':
        href=node.get('href','')
        if href.startswith('https://www.google.com/url?'):href=parse_qs(urlparse(href).query).get('q',[href])[0]
        href=unquote(href)
        if 'perspekt1va.github.io/#web-interface' in href:href='#web-panel'
        if 'perspekt1va.github.io/#reset' in href:href='#reset'
        if href.startswith('#'):href='#'+id_map.get(href[1:],href[1:])
        extra=' target="_blank" rel="noopener noreferrer"' if href.startswith(('http:','https:')) else ''
        return f'<a href="{escape(href,quote=True)}"{extra}>{content}</a>'
    if not text(node) and not node.find('img'):return ''
    attrs=''
    if node.get('id'):
        attrs+=' id="'+escape(id_map.get(node['id'],node['id']),quote=True)+'"'
    if name in ('h1','h2','h3'):
        if node.get('id')=='h.epzg52lcmxmv':name='p';attrs+=' class="image-caption"'
        elif top_heading:name='h1' if node is nodes[0] else 'h2'
        else:name='h3'
    if name=='ol' and node.get('start'):attrs+=f' start="{int(node["start"])}"'
    if name=='p':
        if text(node).startswith(('🚨','⚠️')):attrs+=' class="notice"'
        elif text(node).startswith('💬'):name='blockquote'
        elif node.find('img'):attrs+=' class="image-paragraph"'
    if name not in ('p','ol','ul','li','h1','h2','h3','blockquote'):return content
    return f'<{name}{attrs}>{content}</{name}>'

articles=[]
for i,(sid,title,start,end) in enumerate(sections):
    output=''.join(serialize(n,top_heading=n is nodes[start]) for n in nodes[start:end])
    if sid=='start':
        output=output.replace('<p>','<p class="connection-detail">')
    if sid=='restore':
        parsed=BeautifulSoup(output,'html.parser')
        command=next(p for p in parsed.find_all('p') if 'sh <(wget' in p.get_text())
        before,script=command.get_text().split('sh <(wget',1)
        replacement=BeautifulSoup('<p>'+escape(before.strip())+'</p><div class="code-block"><div class="code-header"><span>Команда установки</span><button type="button" class="copy-button">Копировать</button></div><pre><code>'+escape('sh <(wget'+script)+'</code></pre></div>','html.parser')
        command.replace_with(replacement)
        output=str(parsed)
    articles.append(f'<section class="guide-section" data-section="{sid}" aria-labelledby="{sid}"><div class="section-kicker">'+('РУКОВОДСТВО ПОЛЬЗОВАТЕЛЯ' if i==0 else f'РАЗДЕЛ {i:02}')+'</div>'+output+'</section>')

nav=''.join(f'<a href="#{sid}" class="nav-link"><span class="nav-number">{i:02}</span><span>{title}</span></a>' for i,(sid,title,_,_) in enumerate(sections))
nav='<a class="guide-switch" href="ax3000t.html"><small>ОТДЕЛЬНОЕ РУКОВОДСТВО</small><strong>Xiaomi AX3000T ↗</strong><span>OpenWrt + Podkop</span></a>'+nav
template=(ROOT/'scripts/page-template.html').read_text(encoding='utf-8')
html=template.replace('{{NAV}}',nav).replace('{{CONTENT}}','\n'.join(articles))
(ROOT/'index.html').write_text(html,encoding='utf-8')

# Assert that all retained source sections survive unchanged, in order.
result=BeautifulSoup(html,'html.parser')
for kicker in result.select('.section-kicker,.code-header'):kicker.decompose()
def normalize(value):return re.sub(r'\s+','',value.replace('\u200b',''))
original=normalize(''.join(node.get_text() for _,_,start,end in sections for node in nodes[start:end]))
converted=normalize(''.join(s.get_text() for s in result.select('.guide-section')))
assert original==converted, 'Source text differs from generated guide'
assert len(images)==len(source.find_all('img'))==27
ids={n['id'] for n in result.find_all(id=True)}
assert len(ids)==len(result.find_all(id=True)), 'Duplicate IDs'
for a in result.select('a[href^="#"]'):
    assert a['href'][1:] in ids, f'Broken anchor: {a["href"]}'
(ROOT/'artifacts').mkdir(exist_ok=True)
(ROOT/'artifacts/content-check.json').write_text(json.dumps({'text_preserved':True,'images':len(images),'sections':len(sections),'characters_without_whitespace':len(original)},ensure_ascii=False,indent=2),encoding='utf-8')
print(f'Validated: all {len(original)} text characters, {len(images)} images, {len(sections)} sections, all internal links.')
