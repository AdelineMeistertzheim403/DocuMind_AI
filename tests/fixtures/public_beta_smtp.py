"""Internal disposable SMTP capture, never a relay. Test certificates and messages only."""
import os
import queue
from pathlib import Path

from tests.fake_smtp import FakeSMTP


if __name__=='__main__':
    assert os.environ.get('DOCUMIND_TEST_ONLY')=='sprint-14-6'
    destination=Path('/capture')
    with FakeSMTP((Path('/certs/recipe.crt'),Path('/certs/recipe.key')),
                  starttls=True,host='0.0.0.0',port=8025) as smtp:
        index=0
        while True:
            try:message=smtp.messages.get(timeout=1)
            except queue.Empty:continue
            index+=1
            target=destination/f'message-{index:04d}.eml'
            with target.open('xb') as output:output.write(message)
