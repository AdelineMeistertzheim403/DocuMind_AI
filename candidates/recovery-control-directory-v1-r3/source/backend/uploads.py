"""One bounded file, strict end-of-multipart, and unconditional parser cleanup."""
from fastapi import HTTPException
from starlette.formparsers import MultiPartException, MultiPartParser


class UploadParser(MultiPartParser):
    def __init__(self, request):
        super().__init__(request.headers, request.stream(), max_files=1, max_fields=0)
        self.maximum = request.app.state.settings.max_upload_bytes
        self.file_bytes = 0
        self.ended = False

    def on_headers_finished(self):
        super().on_headers_finished()
        if self._current_part.field_name != 'file' or self._current_part.file is None:
            raise MultiPartException('Un seul fichier nommé file est accepté')

    def on_part_data(self, data, start, end):
        self.file_bytes += end - start
        if self.file_bytes > self.maximum:
            raise HTTPException(413, 'Fichier trop volumineux')
        super().on_part_data(data, start, end)

    def on_end(self):
        self.ended = True
        super().on_end()

    async def parse(self):
        try:
            form = await super().parse()
            if not self.ended or len(form.multi_items()) != 1 or 'file' not in form:
                raise HTTPException(400, 'Multipart incomplet ou invalide')
            return form
        except BaseException:
            for stream in self._files_to_close_on_error:
                stream.close()
            raise


async def parse_upload(request):
    content_type = request.headers.get('content-type', '')
    if not content_type:
        raise HTTPException(422, 'Fichier requis')
    if content_type.split(';', 1)[0].strip().lower() != 'multipart/form-data':
        raise HTTPException(415, 'Multipart requis')
    try:
        return await UploadParser(request).parse()
    except MultiPartException:
        raise HTTPException(400, 'Multipart incomplet ou invalide') from None
