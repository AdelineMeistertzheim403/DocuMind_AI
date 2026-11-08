"""Remove ONLY resources from an explicitly selected, newly created local beta recipe."""
import argparse
import json
from pathlib import Path
import re
import subprocess


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('recipe',type=Path)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    directory=args.recipe.resolve()
    assert directory.parent==root/'var' and re.fullmatch('s14-6-recipe-[a-f0-9]{4,12}',directory.name)
    config=json.loads((directory/'recipe.json').read_text());project=config['project']
    assert project=='documind-'+directory.name
    docker=config['compose'][:3]
    assert docker==['docker','--host','npipe:////./pipe/dockerDesktopLinuxEngine']
    def output(*args):return subprocess.check_output(docker+list(args),text=True).split()
    ids=output('ps','-a','-q','--filter','label=com.docker.compose.project='+project)
    networks=output('network','ls','-q','--filter','label=com.docker.compose.project='+project)
    volumes=output('volume','ls','-q','--filter','label=com.docker.compose.project='+project)
    if ids:
        for item in json.loads(subprocess.check_output(docker+['inspect',*ids],text=True)):
            assert item['Config']['Labels']['com.docker.compose.project']==project
            assert item['Config']['Labels']['documind.test']=='sprint-14-6'
    for name in volumes:
        assert name==project+'_recipe_documents'
        item=json.loads(subprocess.check_output(docker+['volume','inspect',name],text=True))[0]
        assert item['Labels']['documind.test']=='sprint-14-6'
    for name in networks:
        item=json.loads(subprocess.check_output(docker+['network','inspect',name],text=True))[0]
        assert item['Labels']['documind.test']=='sprint-14-6'
    print(json.dumps({'project':project,'containers':len(ids),'networks':len(networks),'volumes':len(volumes),'simulation':not args.execute}))
    if args.execute:
        if ids:
            subprocess.run(docker+['stop','--time','150',*ids],check=True,timeout=180,capture_output=True)
            subprocess.run(docker+['rm',*ids],check=True,capture_output=True)
        if networks:subprocess.run(docker+['network','rm',*networks],check=True,capture_output=True)
        if volumes:subprocess.run(docker+['volume','rm',*volumes],check=True,capture_output=True)
        assert not output('ps','-a','-q','--filter','label=com.docker.compose.project='+project)
        assert not output('network','ls','-q','--filter','label=com.docker.compose.project='+project)
        assert not output('volume','ls','-q','--filter','label=com.docker.compose.project='+project)


if __name__=='__main__':main()
