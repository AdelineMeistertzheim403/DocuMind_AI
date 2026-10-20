"""Original PDF/TXT extraction algorithm, independent from the application."""


def extract(data, extension, max_pages, max_chars):
    import pymupdf as fitz

    if extension == '.txt':
        if data.startswith((b'%PDF-', b'PK\x03\x04', b'MZ', b'\x89PNG', b'\xff\xd8\xff')):
            raise ValueError('invalid_document')
        text = data.decode('utf-8-sig')
        if any(ord(c) < 32 and c not in '\n\r\t\f' for c in text):
            raise ValueError('invalid_document')
        pages = [text]
    elif extension == '.pdf':
        if not data[:8].startswith(b'%PDF-'): raise ValueError('invalid_document')
        with fitz.open(stream=data, filetype='pdf') as document:
            if not document.is_pdf or document.needs_pass or document.is_repaired:
                raise ValueError('invalid_document')
            if not 0 < document.page_count <= max_pages: raise ValueError('invalid_document')
            pages = []; total = 0
            for page in document:
                text = page.get_text('text', sort=True)
                total += len(text)
                if total > max_chars: raise ValueError('invalid_document')
                pages.append(text)
    else:
        raise ValueError('invalid_document')
    if sum(map(len, pages)) > max_chars or not any(text.strip() for text in pages):
        raise ValueError('invalid_document')
    return pages
