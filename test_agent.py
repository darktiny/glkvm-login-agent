import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
import agent

class PolicyTests(unittest.TestCase):
    def test_fail_closed(self):
        good={'login':True,'confidence':.95,'user_matches':True,'empty':True,'field_1000':[500,600]}
        self.assertEqual(agent.decision(good),[.5,.6])
        for change in [{'login':'true'},{'confidence':float('nan')},{'confidence':True},{'field_1000':[2000,600]}, {'empty':False},{'field_1000':None}]:
            self.assertIsNone(agent.decision(good|change))
        for bad in [None,[],True,{'login':True}]: self.assertIsNone(agent.decision(bad))

    def test_reject_reasons_and_threshold_boundary(self):
        good={'login':True,'confidence':.95,'empty':True,'field_1000':[500,600]}
        cases=[({'login':False},'not_mac_login_page'),
               ({'empty':False},'password_field_not_empty'),
               ({'empty':None},'password_field_uncertain'),
               ({'confidence':.849},'low_confidence'),
               ({'confidence':float('nan')},'invalid_model_output'),
               ({'field_1000':[500,2000]},'invalid_field_coordinates')]
        for patch_value,expected in cases:
            with self.subTest(reason=expected):
                d=good|patch_value
                self.assertEqual(agent.rejection_reason(d),expected)
                self.assertIsNone(agent.decision(d))
        self.assertEqual(agent.decision(good|{'confidence':.85}),[.5,.6])
        self.assertIsNone(agent.confidence_value({'confidence':'private arbitrary text'}))

    def test_coordinate_contract_and_diagnostics(self):
        good={'login':True,'confidence':.9,'empty':True,'field_1000':[30,970]}
        self.assertEqual(agent.decision(good),[.03,.97])
        self.assertIsNone(agent.coordinate_issue(good))
        for field,issue in [(None,'missing_coordinates'),({'x':.5,'y':.6},'expected_array'),
                            ([500],'expected_two_values'),(['500','600'],'non_numeric_coordinates'),
                            ([float('inf'),600],'non_finite_coordinates'),([500,1001],'coordinates_outside_0_1000'),([.5,.6],'expected_integer_coordinates')]:
            d=good|{'field_1000':field}
            with self.subTest(issue=issue):
                self.assertIsNone(agent.decision(d))
                self.assertEqual(agent.coordinate_issue(d),issue)
        self.assertNotIn('coordinates',agent.coordinate_diagnostics(good|{'field_1000':['private','text']}))
        self.assertEqual(agent.coordinate_diagnostics(good|{'field_1000':[500,600]})['coordinates'],[500,600])

    def test_explicit_thousand_scale(self):
        result={'login':True,'confidence':.85,'empty':True,'field_1000':[512,905]}
        self.assertEqual(agent.decision(result),[.512,.905])
        self.assertEqual(agent.coordinate_diagnostics(result)['coordinate_space'],'0_1000')
        old={'login':True,'confidence':.95,'empty':True,'field':[512,905]}
        self.assertIsNone(agent.decision(old))
        self.assertEqual(agent.coordinate_issue(old),'missing_coordinates')

    def test_private_secrets(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'s';p.write_text('dummy\n');p.chmod(0o600)
            self.assertEqual(agent.secret(p),'dummy')
            p.chmod(0o644)
            with self.assertRaises(ValueError): agent.secret(p)

class StreamerTests(unittest.IsolatedAsyncioTestCase):
    async def test_delayed_start_can_pass_after_old_poll_limit(self):
        class Reply:
            status=200
            async def __aenter__(self):return self
            async def __aexit__(self,*a):pass
            async def json(self):
                return {'result':{'streamer':None if session.calls <= 45 else {'hdmi':{'signal':True}}}}
        class Session:
            calls=0
            def get(self,*a):
                self.calls+=1
                return Reply()
        session=Session()
        with patch('agent.asyncio.sleep',new=AsyncMock()):
            await agent.Device(session,'unused').wait_for_signal()
        self.assertEqual(session.calls,46)

    async def test_start_deadline_is_bounded_and_reports_observation(self):
        class Reply:
            status=200
            async def __aenter__(self):return self
            async def __aexit__(self,*a):pass
            async def json(self):return {'result':{'streamer':state}}
        class Session:
            def get(self,*a):return Reply()
        for state,expected in [(None,None),({'hdmi':{'signal':False}},False)]:
            with self.subTest(state=state):
                with self.assertRaises(agent.AgentError) as caught:
                    await agent.Device(Session(),'unused').wait_for_signal(timeout=.01)
                self.assertEqual(caught.exception.code,'streamer_start_timeout')
                self.assertEqual(caught.exception.details,{'hdmi_signal':expected})

    async def test_streamer_http_error_is_not_missing_signal(self):
        class Reply:
            status=503
            async def __aenter__(self):return self
            async def __aexit__(self,*a):pass
        class Session:
            def get(self,*a):return Reply()
        with self.assertRaises(agent.AgentError) as caught:
            await agent.Device(Session(),'unused').wait_for_signal()
        self.assertEqual(caught.exception.code,'streamer_http_error')
        self.assertEqual(caught.exception.details,{'http_status':503})


class HidTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_press_releases_and_never_types(self):
        d=agent.Device(None,'unused');calls=[]
        async def post(path,params=None,data=None):
            calls.append((path,params,data))
            if params and params.get('state')=='true': raise RuntimeError('failure')
        d.post=post
        with self.assertRaises(RuntimeError): await d.login([.5,.6],'dummy')
        self.assertEqual(calls[-1][1]['state'],'false')
        self.assertFalse(any(x[0]=='/hid/print' for x in calls))

    async def test_local_password_and_enter(self):
        d=agent.Device(None,'unused');d.post=AsyncMock()
        with patch('agent.asyncio.sleep',new=AsyncMock()): await d.login([.5,.6],'dummy')
        calls=d.post.call_args_list
        printing=[x for x in calls if x.args[0]=='/hid/print']
        self.assertEqual(len(printing),1)
        self.assertEqual(printing[0].args[2],b'dummy')
        self.assertEqual(calls[-1].args[1],{'key':'Enter','state':'false'})


class RunTests(unittest.IsolatedAsyncioTestCase):
    async def test_nonlogin_never_types(self):
        from argparse import Namespace
        from PIL import Image
        import io
        data=io.BytesIO();Image.new('RGB',(960,540)).save(data,'JPEG')
        class Context:
            async def __aenter__(self):return self
            async def __aexit__(self,*a):pass
        device=agent.Device(None,'unused')
        device.capture=AsyncMock(return_value=data.getvalue())
        device.login=AsyncMock()
        config={'kvm_password_file':'unused','api_key_file':'unused','decoder':'unused'}
        args=Namespace(capture=None,dry_run=False,password='dummy')
        with patch('agent.secret',return_value='dummy'),patch('agent.aiohttp.ClientSession',return_value=Context()),patch('agent.Device',return_value=device),patch('agent.classify',new=AsyncMock(return_value={'login':False})):
            self.assertEqual(await agent.run(config,args),2)
        device.login.assert_not_awaited()

    async def test_single_command_submits_once(self):
        from argparse import Namespace
        from PIL import Image
        import io
        data=io.BytesIO();Image.new('RGB',(960,540)).save(data,'JPEG')
        class Context:
            async def __aenter__(self):return self
            async def __aexit__(self,*a):pass
        device=agent.Device(None,'unused');device.capture=AsyncMock(return_value=data.getvalue());device.login=AsyncMock()
        model=AsyncMock(return_value={'login':True,'confidence':.95,'empty':True,'field_1000':[500,600]})
        with patch('agent.secret',return_value='dummy'),patch('agent.aiohttp.ClientSession',return_value=Context()),patch('agent.Device',return_value=device),patch('agent.classify',new=model):
            self.assertEqual(await agent.run({'kvm_password_file':'unused','api_key_file':'unused','decoder':'unused'},Namespace(capture=None,dry_run=False,password='dummy')),0)
        model.assert_awaited_once()
        device.login.assert_awaited_once_with([.5,.6],'dummy')

class ModelTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_http_failure_reports_stage_without_body(self):
        class Reply:
            status=429
            async def __aenter__(self):return self
            async def __aexit__(self,*a):pass
        class Session:
            def post(self,*a,**kw):return Reply()
        with self.assertRaises(agent.AgentError) as caught:
            await agent.classify(Session(),{},b'image')
        self.assertEqual(caught.exception.code,'model_http_error')
        self.assertEqual(caught.exception.details,{'http_status':429})

    async def test_only_image_and_fixed_instruction_go_to_deepseek(self):
        class Reply:
            status=200
            async def __aenter__(self):return self
            async def __aexit__(self,*a):pass
            @property
            def content(self):return self
            async def read(self,n):
                return json.dumps({'choices':[{'finish_reason':'stop','message':{'content':'{"login":false}'}}]}).encode()
        class Session:
            def post(self,url,**kw):
                self.url,self.kw=url,kw
                return Reply()
        session=Session()
        result=await agent.classify(session,{},b'image')
        body=session.kw['json']
        self.assertFalse(result['login'])
        self.assertEqual(body['thinking'],{'type':'disabled'})
        self.assertEqual(len(body['messages']),1)
        self.assertEqual(body['messages'][0]['content'][1]['image_url']['detail'],'original')
        self.assertFalse(session.kw['allow_redirects'])
        self.assertNotIn('password_file',str(body))

if __name__=='__main__':unittest.main()
