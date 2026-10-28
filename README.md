# publicador

Publica os carrosséis do @obrunomendonca direto no Instagram, no horário marcado.

## Como funciona

Cada post é uma pasta com os slides em JPEG, a legenda e a data:

```
posts/
  rascunhos/    preparando, nada aqui é publicado
  agendados/    aprovado, sai sozinho quando chegar a hora
  publicados/   já foi, com o link do post no post.json
```

Dentro de cada pasta:

- `01.jpg`, `02.jpg`… os slides, na ordem do nome (1 a 10, 1080×1350; com 1 vira post simples)
- `legenda.txt` a legenda, do jeito que vai pro Instagram
- `post.json` a data, com fuso: `{"publicar_em": "2026-10-28T19:00:00-03:00"}`. Pra story, acrescenta `"tipo": "story"` (imagem 1080×1920, sem legenda; cada imagem vira um story)

**Aprovar um post é mover a pasta de `rascunhos` pra `agendados`.** O GitHub roda a cada 30 minutos, publica o que estiver vencido e move a pasta pra `publicados`.

## Rodar na mão

Em **Actions › Publicar › Run workflow**:

- `verificar` confere token, conta e cota sem publicar nada
- `publicar` com uma pasta preenchida publica aquela pasta na hora, ignorando a data

## Segredos

Em **Settings › Secrets and variables › Actions**:

- `IG_ACCESS_TOKEN` token da Meta (vence em uns 60 dias, precisa renovar)
- `IG_USER_ID` ID da conta do Instagram

## Atenção

O repositório é público porque a Meta busca as imagens pela URL. Quem fuçar vê o que tá em `agendados` antes da hora.

## Token

O `token.json` guarda só a data em que o token foi gerado (nunca o token). Um vigia semanal usa essa data pra avisar antes de vencer. Ao gerar um token novo, atualiza `gerado_em`.
