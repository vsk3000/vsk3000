"""Build the separate AX3000T guide, reusing the site's layout and own document."""
from pathlib import Path
from html import escape
from concurrent.futures import ThreadPoolExecutor
import re, sys, urllib.request, subprocess, struct
ROOT=Path(__file__).resolve().parents[1]
snapshot=ROOT/'site-content/ax3000t.html'
if snapshot.exists():
    (ROOT/'ax3000t.html').write_bytes(snapshot.read_bytes())
    print('Restored ax3000t.html from the visual editor snapshot.')
    sys.exit(0)
sys.path.insert(0,str(ROOT/'.tools'))
from bs4 import BeautifulSoup

main=BeautifulSoup((ROOT/'index.html').read_text(encoding='utf-8'),'html.parser')
content=(ROOT/'scripts/ax3000t-content.html').read_text(encoding='utf-8')
mapping={s['data-section']:'ax-'+s['data-section'] for s in main.select('.guide-section')}
mapping.update({'start':'ax-start','connection':'ax-connect','restore':'ax-backup','web-panel':'ax-login','reset':'ax-reset','troubleshooting':'ax-diagnostics'})
for placeholder,section_id in [('MAIN_ROUTER','main-router'),('WIFI','wifi')]:
    block=main.select_one(f'[data-section="{section_id}"]')
    block['data-section']='ax-'+section_id
    block['aria-labelledby']='ax-'+section_id
    block.select_one('.section-kicker').string='НАСТРОЙКИ OPENWRT'
    for el in block.select('[id]'):
        el['id']='ax-'+el['id']
    for link in block.select('a[href^="#"]'):
        old=link['href'][1:]
        link['href']='#'+mapping.get(old,'ax-'+old)
    if section_id=='main-router':
        reset_step=block.select_one('a[href="#ax-reset"]').find_parent('li')
        reset_step.clear()
        reset_step.append('Не сбрасывайте AX3000T. Если страница авторизации не открывается, проверьте подключение и обратитесь ко мне через профиль на Авито.')
        intro=BeautifulSoup('<p class="notice">Этот раздел относится к интернет-соединению AX3000T с провайдером. Настраивайте обычный доступ в интернет до проверки маршрутизации Podkop; затем вернитесь к <a href="#ax-diagnostics">диагностике</a>.</p>','html.parser')
        block.h2.insert_after(intro)
    content=content.replace('{{'+placeholder+'}}',str(block))

doc=BeautifulSoup(content,'html.parser')
source=BeautifulSoup((ROOT/'source-materials/perspektiva.html').read_text(encoding='utf-8'),'html.parser')
available={im.get('src'):im.get('alt','Настройки роутера') for im in source.select('img[src]')}
assets=ROOT/'assets/ax3000t'
assets.mkdir(exist_ok=True)
requests={}
for gallery in doc.select('[data-gallery]'):
    for number in gallery['data-gallery'].split(','):
        source_path=f'img/{number}.png'
        assert source_path in available,source_path
        requests[number]=(source_path,available[source_path])

def download(item):
    number,(path,_) = item
    target=assets/f'{number}.png'
    if not target.exists():
        data=urllib.request.urlopen('https://perspekt1va.github.io/'+path,timeout=30).read()
        assert data.startswith(b'\x89PNG'),path
        target.write_bytes(data)
    return number
with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(download,requests.items()))

for gallery in doc.select('[data-gallery]'):
    html=''
    for number in gallery['data-gallery'].split(','):
        alt=escape(requests[number][1],quote=True)
        path=f'assets/ax3000t/{number}.png'
        html+=f'<a class="screenshot" data-lightbox href="{path}"><img src="{path}" alt="{alt}" loading="lazy" decoding="async"></a>'
    gallery.replace_with(BeautifulSoup(html,'html.parser'))

short_names=['Начало работы','Подключение и вход','Подписка и домены','Выбор сервера','FullVPN','VPN для устройства','Диагностика','DNS и FakeIP','Обновление серверов','Бекап AX3000T','Не сбрасывайте роутер','Интернет от провайдера','Название и пароль Wi-Fi']
sections=doc.select('.guide-section')
assert len(short_names)==len(sections)
nav='<a class="guide-switch" href="index.html"><small>ДРУГАЯ ИНСТРУКЦИЯ</small><strong>Xiaomi 4C/4A ↗</strong></a>'
for i,(section,title) in enumerate(zip(sections,short_names)):
    nav+=f'<a class="nav-link" href="#{section["data-section"]}"><span class="nav-number">{i:02}</span><span>{title}</span></a>'
template=(ROOT/'scripts/page-template.html').read_text(encoding='utf-8')
html=template.replace('{{NAV}}',nav).replace('{{CONTENT}}',str(doc))
html=html.replace('<title>Руководство пользователя роутера</title>','<title>Xiaomi AX3000T — руководство OpenWrt и Podkop</title>')
html=html.replace('content="Руководство пользователя роутера: подключение, настройка Wi-Fi и восстановление. Пошаговые инструкции с изображениями."','content="Xiaomi AX3000T с OpenWrt и Podkop: подключение, серверы, FullVPN, DNS, диагностика, бекап и восстановление."')
html=html.replace('href="#start"','href="#ax-start"').replace('Роутер</strong>','AX3000T</strong>').replace('Всё о вашем роутере','Xiaomi AX3000T · Podkop')
result=BeautifulSoup(html,'html.parser')
ids={node['id'] for node in result.select('[id]')}
assert len(ids)==len(result.select('[id]'))
for link in result.select('a[href^="#"]'):assert link['href'][1:] in ids,link
for img in result.select('img[src]'):assert (ROOT/img['src']).exists(),img
for img in result.select('img[src$=".png"]'):
    data=(ROOT/img['src']).read_bytes()
    img['width'],img['height']=struct.unpack('>II',data[16:24])
assert not result.select('[data-section="telegram"]')
assert 'Zapret-Manager.sh' not in html
(ROOT/'ax3000t.html').write_bytes(str(result).encode('utf-8'))
print(f'AX3000T: {len(sections)} sections, {len(result.select("img[src]"))} illustrations; all internal links and assets verified.')
