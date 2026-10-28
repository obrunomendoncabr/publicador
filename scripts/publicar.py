"""Publicador de carrosséis no Instagram.

Modos:
  python scripts/publicar.py verificar        confere token, conta e cota, sem publicar nada
  python scripts/publicar.py publicar         publica o que estiver vencido em posts/agendados
  python scripts/publicar.py publicar PASTA   publica uma pasta específica, ignorando a data

Lê IG_ACCESS_TOKEN e IG_USER_ID do ambiente (segredos do GitHub).
As imagens precisam estar no repositório público: a Meta busca cada JPEG pela URL.
"""
import json
import os
import pathlib
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API = "https://graph.instagram.com/" + os.environ.get("IG_API_VERSION", "v23.0")
RAIZ = pathlib.Path(__file__).resolve().parent.parent
AGENDADOS = RAIZ / "posts" / "agendados"
PUBLICADOS = RAIZ / "posts" / "publicados"
REPO = os.environ.get("GITHUB_REPOSITORY", "obrunomendoncabr/publicador")
REF = os.environ.get("GITHUB_SHA", "main")


def segredo(nome):
    valor = os.environ.get(nome, "").strip()
    if not valor:
        sys.exit(f"Faltou o segredo {nome}. Confere em Settings › Secrets and variables › Actions.")
    return valor


TOKEN = None
USER_ID = None


def chamar(metodo, caminho, **params):
    params["access_token"] = TOKEN
    dados = urllib.parse.urlencode(params).encode()
    url = f"{API}/{caminho}"
    if metodo == "GET":
        req = urllib.request.Request(f"{url}?{dados.decode()}")
    else:
        req = urllib.request.Request(url, data=dados, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        corpo = e.read().decode(errors="replace")
        # nunca imprime a URL inteira, ela carrega o token
        sys.exit(f"Erro da Meta em {metodo} {caminho} ({e.code}): {corpo}")


def esperar_pronto(container_id, rotulo):
    for _ in range(30):
        status = chamar("GET", container_id, fields="status_code").get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            sys.exit(f"{rotulo}: a Meta recusou o arquivo (status {status}).")
        time.sleep(5)
    sys.exit(f"{rotulo}: demorou demais pra processar.")


def url_publica(arquivo):
    rel = arquivo.relative_to(RAIZ).as_posix()
    return f"https://raw.githubusercontent.com/{REPO}/{REF}/{urllib.parse.quote(rel)}"


def verificar():
    conta = chamar("GET", "me", fields="user_id,username,account_type")
    print(f"Conta: @{conta.get('username')} ({conta.get('account_type')})")
    if str(conta.get("user_id")) != USER_ID:
        print(f"Atenção: IG_USER_ID ({USER_ID}) é diferente do ID da conta do token ({conta.get('user_id')}).")
    cota = chamar("GET", f"{USER_ID}/content_publishing_limit", fields="config,quota_usage")
    print(f"Cota de publicação: {json.dumps(cota.get('data', cota), ensure_ascii=False)}")
    print("Tudo certo, dá pra publicar.")


def publicar_pasta(pasta):
    imagens = sorted(p for p in pasta.iterdir() if p.suffix.lower() in (".jpg", ".jpeg"))
    if not 1 <= len(imagens) <= 10:
        sys.exit(f"{pasta.name}: o post precisa de 1 a 10 JPEGs, achei {len(imagens)}.")
    legenda_arq = pasta / "legenda.txt"
    legenda = legenda_arq.read_text(encoding="utf-8").strip() if legenda_arq.exists() else ""
    meta_arq = pasta / "post.json"
    meta = json.loads(meta_arq.read_text(encoding="utf-8")) if meta_arq.exists() else {}
    tipo = meta.get("tipo", "feed")

    if tipo == "story":
        # story não tem legenda; cada imagem vira um story, na ordem
        print(f"Publicando {pasta.name} como story ({len(imagens)} imagem(ns))")
        ids = []
        for img in imagens:
            c = chamar("POST", f"{USER_ID}/media", image_url=url_publica(img), media_type="STORIES")
            esperar_pronto(c["id"], img.name)
            ids.append(chamar("POST", f"{USER_ID}/media_publish", creation_id=c["id"])["id"])
            print(f"  {img.name} no ar")
        meta.update({"publicado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "media_ids": ids})
        meta_arq.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        PUBLICADOS.mkdir(parents=True, exist_ok=True)
        shutil.move(str(pasta), str(PUBLICADOS / pasta.name))
        return
    if tipo != "feed":
        sys.exit(f"{pasta.name}: tipo desconhecido '{tipo}' (use feed ou story).")

    print(f"Publicando {pasta.name} com {len(imagens)} imagem(ns)")
    if len(imagens) == 1:
        container = chamar("POST", f"{USER_ID}/media", image_url=url_publica(imagens[0]), caption=legenda)
        esperar_pronto(container["id"], imagens[0].name)
    else:
        filhos = []
        for img in imagens:
            c = chamar("POST", f"{USER_ID}/media", image_url=url_publica(img), is_carousel_item="true")
            esperar_pronto(c["id"], img.name)
            filhos.append(c["id"])
            print(f"  {img.name} ok")
        container = chamar("POST", f"{USER_ID}/media", media_type="CAROUSEL",
                           children=",".join(filhos), caption=legenda)
        esperar_pronto(container["id"], "carrossel")
    publicado = chamar("POST", f"{USER_ID}/media_publish", creation_id=container["id"])
    link = chamar("GET", publicado["id"], fields="permalink").get("permalink")
    print(f"Publicado: {link}")

    meta.update({"publicado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "media_id": publicado["id"], "link": link})
    meta_arq.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    PUBLICADOS.mkdir(parents=True, exist_ok=True)
    shutil.move(str(pasta), str(PUBLICADOS / pasta.name))


def vencidos():
    agora = datetime.now(timezone.utc)
    for pasta in sorted(p for p in AGENDADOS.iterdir() if p.is_dir()):
        meta_arq = pasta / "post.json"
        if not meta_arq.exists():
            print(f"{pasta.name}: sem post.json, pulando.")
            continue
        quando = json.loads(meta_arq.read_text(encoding="utf-8")).get("publicar_em")
        if not quando:
            print(f"{pasta.name}: sem publicar_em, pulando.")
            continue
        alvo = datetime.fromisoformat(quando)
        if alvo.tzinfo is None:
            sys.exit(f"{pasta.name}: publicar_em precisa de fuso, tipo 2026-10-28T19:00:00-03:00")
        if alvo <= agora:
            yield pasta
        else:
            print(f"{pasta.name}: agendado pra {quando}, ainda não.")


def main():
    global TOKEN, USER_ID
    modo = sys.argv[1] if len(sys.argv) > 1 else "verificar"
    TOKEN, USER_ID = segredo("IG_ACCESS_TOKEN"), segredo("IG_USER_ID")
    if modo == "verificar":
        verificar()
    elif modo == "publicar":
        if len(sys.argv) > 2 and sys.argv[2].strip():
            pasta = (RAIZ / sys.argv[2].strip()).resolve()
            if not pasta.is_dir() or RAIZ not in pasta.parents:
                sys.exit(f"Pasta não encontrada: {sys.argv[2]}")
            publicar_pasta(pasta)
        else:
            fila = list(vencidos())
            if not fila:
                print("Nada pra publicar agora.")
            for pasta in fila:
                publicar_pasta(pasta)
    else:
        sys.exit(f"Modo desconhecido: {modo}")


if __name__ == "__main__":
    main()
