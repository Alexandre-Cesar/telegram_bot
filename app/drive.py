import io

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from . import config
from .google_auth import get_credentials

_folder_id: str | None = None  # cache: só procura/cria a pasta uma vez por execução


def _pasta_id(service) -> str:
    """Acha (ou cria) a pasta do bot.

    Com o escopo drive.file o app só enxerga o que ele mesmo criou, então a pasta
    precisa ser criada pelo bot: uma pasta criada à mão no Drive devolve 404.
    """
    global _folder_id
    if _folder_id:
        return _folder_id

    nome = config.DRIVE_FOLDER_NAME
    escapado = nome.replace("\\", "\\\\").replace("'", "\\'")
    consulta = (
        f"name = '{escapado}' and mimeType = 'application/vnd.google-apps.folder' "
        "and trashed = false"
    )
    achados = service.files().list(q=consulta, fields="files(id)", pageSize=1).execute().get("files", [])
    if achados:
        _folder_id = achados[0]["id"]
    else:
        pasta = service.files().create(
            body={"name": nome, "mimeType": "application/vnd.google-apps.folder"},
            fields="id",
        ).execute()
        _folder_id = pasta["id"]
    return _folder_id


def upload_foto(conteudo: bytes, nome: str, mime: str) -> str:
    """Envia a foto para a pasta do bot no Drive e devolve o link de visualização."""
    service = build("drive", "v3", credentials=get_credentials(), cache_discovery=False)
    media = MediaIoBaseUpload(io.BytesIO(conteudo), mimetype=mime)
    arq = service.files().create(
        body={"name": nome, "parents": [_pasta_id(service)]},
        media_body=media,
        fields="id, webViewLink",
    ).execute()
    return arq["webViewLink"]
