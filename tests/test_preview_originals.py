import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'shared/scripts'))
from PIL import Image
from preview_originals import compose, insertion_errors, insert_pages, sha
from workflow_lib import schema_errors, stop_point_status
import workflow


class OriginalInsertionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        (self.project/'04_full-preview/assets').mkdir(parents=True)
        (self.project/'02_design').mkdir()
        Image.new('RGB', (1920,1080), '#123456').save(self.project/'04_full-preview/assets/GEN-001.png')
        Image.new('RGB', (400,200), '#CE4020').save(self.project/'original.png')
        self.image = {'id':'IMG-001','sourceId':'MAT-001','path':'original.png',
                      'box':{'x':.1,'y':.2,'w':.4,'h':.4}, 'fit':'contain'}
        self.plan = {'id':'S01','images':[self.image]}
        self.record = {'status':'complete','output':'04_full-preview/assets/GEN-001.png',
                       'sha256':sha(self.project/'04_full-preview/assets/GEN-001.png')}
        self.page = {'id':'S01','jobId':'JOB-001','file':'04_full-preview/slides/S01.png',
                     'sha256':self.record['sha256'],'promptSummary':'测试','review':'旧审阅'}
        self.manifest = {'version':1,'stage':'2.2','styleConstraints':'蓝色','pages':[self.page]}
        for name, obj in [('02_design/image-plan.json',{'slides':[self.plan]}),
                          ('04_full-preview/previews.json',self.manifest),
                          ('04_full-preview/generation-ledger.json',{'jobs':{'JOB-001':self.record}})]:
            (self.project/name).write_text(json.dumps(obj), encoding='utf-8')

    def insert(self):
        insert_pages(self.project)
        return json.loads((self.project/'04_full-preview/previews.json').read_text())['pages'][0]

    def test_real_insertion_preserves_provider_and_resets_review(self):
        before = (self.project/self.record['output']).read_bytes()
        page = self.insert()
        self.assertEqual(before, (self.project/self.record['output']).read_bytes())
        self.assertEqual('', page['review'])
        self.assertEqual([], insertion_errors(self.project,page,self.plan,self.record))
        self.manifest['pages']=[page]
        self.assertEqual([],schema_errors(self.manifest,'preview-pages'))
        with Image.open(self.project/page['file']) as im:
            self.assertEqual((206,64,32),im.getpixel((500,430)))
            self.assertEqual((255,255,255),im.getpixel((500,220)))  # contain letterbox

    def test_empty_frame_cannot_be_claimed_as_inserted(self):
        page=self.insert()
        Image.open(self.project/self.record['output']).save(self.project/page['file'])
        self.assertTrue(insertion_errors(self.project,page,self.plan,self.record))

    def test_changed_original_and_false_provider_rejected(self):
        page=self.insert()
        Image.new('RGB',(400,200),'green').save(self.project/'original.png')
        self.assertTrue(insertion_errors(self.project,page,self.plan,self.record))
        record=dict(self.record,sha256='0'*64)
        self.assertTrue(insertion_errors(self.project,page,self.plan,record))

    def test_missing_inserted_records_rejected(self):
        self.assertTrue(insertion_errors(self.project,self.page,self.plan,self.record))
        self.assertTrue(schema_errors(self.manifest,'preview-pages'))
        page=self.insert(); page['originals']=[]
        self.assertTrue(insertion_errors(self.project,page,self.plan,self.record))

    def test_carrier_cleanup_keeps_complete_original_in_inner_frame(self):
        page=self.insert()
        page['originals'][0]['clearBox']={'x':.05,'y':.1,'w':.5,'h':.6}
        result=compose(self.project,page['providerFile'],page['originals'])
        result.save(self.project/page['file'])
        self.assertEqual([],insertion_errors(self.project,page,self.plan,self.record))
        self.assertEqual((255,255,255),result.getpixel((110,150)))
        page['originals'][0]['clearBox']={'x':.2,'y':.2,'w':.1,'h':.1}
        self.assertTrue(insertion_errors(self.project,page,self.plan,self.record))

    def test_waiting_stop_point_rejects_incomplete_original_insertion(self):
        (self.project/'workflow-state.json').write_text(json.dumps({'stages':{'2.2':{'status':'awaiting_user'}}}))
        with patch('workflow_lib.preview_pages_errors',return_value=['未插入原图']):
            self.assertFalse(stop_point_status(self.project)['canStop'])
        with patch('workflow_lib.preview_pages_errors',return_value=[]):
            self.assertTrue(stop_point_status(self.project)['canStop'])

    def test_await_command_checks_insertion_before_writing_state(self):
        state=self.project/'workflow-state.json'
        state.write_text(json.dumps({'stages':{'2.2':{'status':'not_started'}}}))
        args=SimpleNamespace(command='await',stage='2.2',notes='测试')
        before=state.read_bytes()
        with patch('workflow.preview_pages_errors',return_value=['未插入原图']), patch('workflow.generation_evidence_errors',return_value=[]):
            with self.assertRaisesRegex(ValueError,'先插入原图'):
                workflow._dispatch(self.project,args)
        self.assertEqual(before,state.read_bytes())
        with patch('workflow.preview_pages_errors',return_value=[]), patch('workflow.generation_evidence_errors',return_value=[]):
            workflow._dispatch(self.project,args)
        self.assertEqual('awaiting_user',json.loads(state.read_text())['stages']['2.2']['status'])


if __name__ == '__main__':
    unittest.main()
