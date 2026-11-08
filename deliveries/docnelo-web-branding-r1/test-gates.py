"""Offline adversarial tests for the proposed read-only deployment checks."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PAYLOAD = Path(__file__).resolve().parent / 'payload'
sys.path.insert(0, str(PAYLOAD))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, PAYLOAD / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


compose = load('compose_gate', 'check-compose.py')
state = load('state_gate', 'verify-state.py')


class Gates(unittest.TestCase):
    def compose_case(self, mutation=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            file = root / 'compose.public-beta.vps.yaml'
            file.write_text('synthetic', encoding='utf-8')
            cfg = {'name':'documind-public-beta', 'services':{'web':{
                'image':'old', 'environment':{'BFF_BACKEND_URL':'http://api:8000'},
                'labels':{'router':'fixed'}}, 'api':{'image':'fixed-api'}, 'db':{'image':'fixed-db'}},
                'volumes':{'database':'fixed'}}
            updated = copy.deepcopy(cfg)
            updated['services']['web']['image'] = 'new'
            updated['services']['web']['pull_policy'] = 'never'
            current = {'Id':'web-container', 'Image':'base-id', 'Config':{
                'Env':['BFF_BACKEND_URL=http://api:8000'], 'Labels':{
                    'com.docker.compose.project.config_files':str(file)}}}
            proof = {'status':'passed','reference_image_id':'base-id','app_root':str(root),
                'compose_files':[str(file)], 'containers':{'documind-public-beta-web-1':{'id':'web-container'}}}
            image = 'new-id'
            if mutation == 'api': updated['services']['api']['image'] = 'changed'
            if mutation == 'web_label': updated['services']['web']['labels']['router'] = 'changed'
            if mutation == 'env': current['Config']['Env'] = ['BFF_BACKEND_URL=http://wrong:8000']
            if mutation == 'active': current['Image'] = 'different-base'
            if mutation == 'compose': current['Config']['Labels']['com.docker.compose.project.config_files'] = 'other-file'
            if mutation == 'unconfirmed': proof['status'] = 'NO-GO'
            if mutation == 'image': image = 'different-new-image'
            (root / 'proof.json').write_text(json.dumps(proof), encoding='utf-8')
            (root / 'RELEASE.json').write_text(json.dumps({'reference_image_id':'base-id',
                'new_image_id':'new-id','new_image_tag':'new'}), encoding='utf-8')
            def run(argv, **kwargs):
                if 'compose' in argv:
                    return json.dumps(updated if str(root / 'web.r1.override.yaml') in argv else cfg)
                if argv[-1] == 'documind-public-beta-web-1': return json.dumps([current])
                return image
            with patch.object(compose.subprocess, 'check_output', run):
                if mutation:
                    with self.assertRaises(ValueError): compose.check(root / 'proof.json', root)
                else: compose.check(root / 'proof.json', root)

    def state_case(self, mutation=None):
        names=['documind-public-beta-db-1','documind-public-beta-api-1','documind-public-beta-web-1']
        rows=[]; before={}
        for name in names:
            before[name]={'id':name,'image_id':'base-'+name,'started_at':'old','volumes':['fixed']}
            rows.append({'Name':'/'+name,'Id':name,'Image':'new-id' if name.endswith('-web-1') else 'base-'+name,
                'State':{'Running':True,'StartedAt':'old','Health':{'Status':'healthy'}},
                'Mounts':[{'Type':'volume','Name':'fixed'}]})
        options={'registration_mode':'public','public_registration_availability':'closed','terms_version':'original'}
        proof={'origin':'https://synthetic.test','containers':before,'options':copy.deepcopy(options)}
        if mutation == 'restart': rows[1]['State']['StartedAt'] = 'new'
        if mutation == 'volume': rows[0]['Mounts'][0]['Name'] = 'different'
        if mutation == 'web_image': rows[2]['Image'] = 'wrong'
        if mutation == 'unhealthy': rows[2]['State']['Health']['Status'] = 'starting'
        if mutation == 'registration': options['public_registration_availability'] = 'available'
        if mutation == 'legal': options['terms_version'] = 'changed'
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, maximum): return json.dumps(options).encode()
        class Opener:
            def open(self, *args, **kwargs): return Response()
        with patch.object(state.subprocess, 'check_output', return_value=json.dumps(rows)), \
             patch.object(state, 'build_opener', return_value=Opener()):
            if mutation:
                with self.assertRaises(ValueError): state.verify(proof, 'new-id')
            else: state.verify(proof, 'new-id')


for name in (None, 'api', 'web_label', 'env', 'active', 'compose', 'unconfirmed', 'image'):
    setattr(Gates, 'test_compose_' + (name or 'valid'), lambda self, value=name: self.compose_case(value))
for name in (None, 'restart', 'volume', 'web_image', 'unhealthy', 'registration', 'legal'):
    setattr(Gates, 'test_state_' + (name or 'valid'), lambda self, value=name: self.state_case(value))

if __name__ == '__main__':
    unittest.main()
