import copy, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import Editor, PAGES, parse_page, render_page, clean_html, blob_sha
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[2]

class EditorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        for page in PAGES:
            (self.root/page).write_bytes((ROOT/page).read_bytes())
        self.editor=Editor(self.root)
    def tearDown(self): self.tmp.cleanup()
    def test_existing_content_and_images_survive_roundtrip(self):
        for page in PAGES:
            before=BeautifulSoup(self.editor.bases[page],'html.parser')
            after=BeautifulSoup(render_page(self.editor.bases[page],self.editor.models[page]),'html.parser')
            self.assertEqual([x['src'] for x in before.select('img[src]')],[x['src'] for x in after.select('img[src]')])
            for doc in [before,after]:
                for node in doc.select('.section-kicker'): node.decompose()
            self.assertEqual([''.join(x.get_text().split()) for x in before.select('.guide-section')],[''.join(x.get_text().split()) for x in after.select('.guide-section')])
            self.assertEqual(before.select_one('#contacts').get_text(),after.select_one('#contacts').get_text())
    def test_save_restart_and_restore(self):
        model=copy.deepcopy(self.editor.models['index.html'])
        original=model['sections'][0]['title']
        model['sections'][0]['title']='Новый заголовок'
        self.editor.save(model)
        restarted=Editor(self.root)
        self.assertEqual(restarted.models['index.html']['sections'][0]['title'],'Новый заголовок')
        history=next(x for x in self.editor.history() if x['page']=='index.html')
        restored=self.editor.restore(history['id'])
        self.assertEqual(restored['sections'][0]['title'],original)
        self.assertNotIn('Новый заголовок',(self.root/'index.html').read_text(encoding='utf-8'))
    def test_untrusted_paste_is_sanitized(self):
        html=clean_html('<script>alert(1)</script><iframe src="http://evil"></iframe><p onclick="x()">Text</p><a href="javascript:alert(1)">bad</a><img src="file:///secret"><a href="https://example.com">good</a>')
        self.assertNotIn('script',html); self.assertNotIn('onclick',html); self.assertNotIn('iframe',html)
        self.assertNotIn('file:',html); self.assertIn('noopener',html)
    def test_reorder_and_add_keep_menu_consistent(self):
        model=copy.deepcopy(self.editor.models['index.html'])
        model['sections'].insert(0,{'id':'custom-test','title':'Тест','nav':'Коротко','html':'<p>Текст</p>'})
        doc=BeautifulSoup(render_page(self.editor.bases['index.html'],model),'html.parser')
        self.assertEqual(doc.select_one('h1')['id'],'custom-test')
        self.assertEqual(doc.select_one('.brand')['href'],'#custom-test')
        self.assertEqual(doc.select_one('.nav-link')['href'],'#custom-test')
        self.assertEqual(doc.select_one('.nav-link').get_text(),'00Коротко')
    def test_upload_rejects_active_content(self):
        with self.assertRaises(ValueError): self.editor.upload('a.svg','PHN2Zz48L3N2Zz4=')
        with self.assertRaises(ValueError): self.editor.upload('a.png','PHN2Zz48L3N2Zz4=')
    def test_conflict_never_updates_ref_or_local_page(self):
        calls=[]
        def api(path,method='GET',data=None):
            calls.append((path,method))
            if '/git/ref/' in path:return {'object':{'sha':'parent'}}
            if '/git/commits/' in path:return {'tree':{'sha':'tree'}}
            if '/git/trees/' in path:return {'tree':[{'path':'index.html','type':'blob','sha':'changed'}]}
            self.fail('Unexpected write')
        self.editor.api=api
        old=(self.root/'index.html').read_bytes()
        self.editor.publish(copy.deepcopy(self.editor.models))
        self.assertEqual(self.editor.status['stage'],'error')
        self.assertIn('новая версия',self.editor.status['message'])
        self.assertTrue(all(method=='GET' for _,method in calls))
        self.assertEqual((self.root/'index.html').read_bytes(),old)
    def test_broken_section_link_prevents_publication(self):
        models=copy.deepcopy(self.editor.models)
        models['index.html']['sections'][0]['html']+='<a href="#missing-section">Missing</a>'
        def api(path,method='GET',data=None):
            if '/git/ref/' in path:return {'object':{'sha':'parent'}}
            if '/git/commits/' in path:return {'tree':{'sha':'tree'}}
            if '/git/trees/' in path:return {'tree':[]}
            self.fail('Unexpected write')
        self.editor.api=api
        self.editor.publish(models)
        self.assertEqual(self.editor.status['stage'],'error')
        self.assertIn('#missing-section',self.editor.status['message'])
    def test_successful_publish_checks_live_pages_and_saves_snapshot(self):
        calls=[]
        remote=[{'path':p,'type':'blob','sha':blob_sha(self.editor.bases[p])} for p in PAGES]
        def api(path,method='GET',data=None):
            calls.append((path,method,data))
            if '/git/ref/' in path:return {'object':{'sha':'parent'}}
            if '/git/commits/' in path:return {'tree':{'sha':'tree'}}
            if '/git/trees/' in path:return {'tree':remote}
            if path.endswith('/git/trees'):return {'sha':'newtree'}
            if path.endswith('/git/commits'):return {'sha':'newcommit'}
            if '/git/refs/' in path:
                self.assertFalse(data['force']); return {}
            self.fail(path)
        self.editor.api=api
        models=copy.deepcopy(self.editor.models)
        models['index.html']['sections'][0]['title']='Published title'
        expected={p:render_page(self.editor.bases[p],models[p]).encode() for p in PAGES}
        class Response:
            def __init__(self,data):self.data=data
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return self.data
        def live(req,timeout):return Response(expected[req.full_url.split('/')[-1].split('?')[0]])
        with patch('app.time.sleep'),patch('app.urlopen',side_effect=live):self.editor.publish(models)
        self.assertEqual(self.editor.status['stage'],'success')
        for page in PAGES:
            self.assertEqual((self.root/page).read_bytes(),expected[page])
            self.assertEqual((self.root/'site-content'/page).read_bytes(),expected[page])
        treewrite=next(c for c in calls if c[0].endswith('/git/trees') and c[1]=='POST')
        self.assertEqual(len(treewrite[2]['tree']),4)

if __name__=='__main__':unittest.main()
