# Guía de despliegue (Sprint 1)

Click a click, sin asumir nada.

## 1. Instalar lo necesario

### macOS

```bash
# Si no tienes Homebrew:
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Docker Desktop
brew install --cask docker

# Git (suele venir con macOS, pero por si acaso)
brew install git
```

Tras instalar Docker Desktop, ábrelo desde Aplicaciones y deja que arranque.

### Linux (Ubuntu/Debian)

```bash
# Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
# (cerrar sesión y volver para que el grupo aplique)

# Docker Compose viene incluido en Docker Engine moderno.
docker compose version   # comprueba que existe
```

### Windows

Instala **Docker Desktop for Windows** desde docker.com.
Asegúrate de que WSL2 está activado (te lo pide el instalador).
Trabaja desde una terminal WSL (Ubuntu).

## 2. Obtener una API key de PubMed (opcional pero recomendado)

Es **gratis** y multiplica el rate limit por 3.

1. Ve a https://www.ncbi.nlm.nih.gov/account/ y crea cuenta (o entra con Google).
2. Una vez dentro, click en tu nombre arriba a la derecha → **Account settings**.
3. Baja hasta **API Key Management** → **Create an API Key**.
4. Copia la key.

## 3. Clonar y configurar el proyecto

```bash
# Si todavía no lo has subido a GitHub, descomprime el zip donde sea cómodo.
cd ~/projects   # o donde tengas tus proyectos
unzip clinical-intelligence-platform.zip
cd clinical-intelligence-platform

# Opcional: copiar el .env de ejemplo para personalizar credenciales o PubMed
cp .env.example .env

# Editar el .env si lo has creado
# (usa nano, vim, VS Code... lo que tengas)
nano .env
```

En `.env`, pega tu API key de PubMed y cambia el email:

```env
PUBMED_API_KEY=tu_key_aqui
PUBMED_EMAIL=toni@example.com
```

Si no quieres pedir la key ahora, puedes no crear `.env` o dejarla vacía.
Docker Compose y la app usan valores locales por defecto; `.env.example` es la plantilla documentada.

## 4. Levantar la infraestructura

```bash
docker compose up -d --build
```

Esto:
- Construye la imagen de la API.
- Arranca Postgres, MinIO y la API.
- Crea el bucket `pubmed-raw` en MinIO.

Comprueba que todo está corriendo:

```bash
docker compose ps
```

Deberías ver `cip-postgres`, `cip-minio` y `cip-api` con estado `running` o `healthy`.

Si algo no arranca, mira los logs:

```bash
docker compose logs api
docker compose logs postgres
```

## 5. Inicializar la base de datos

Solo la primera vez:

```bash
docker compose exec api python -m cip.db_init
```

Verás algo como:

```
2026-04-28T...  info  creating_tables
2026-04-28T...  info  db_init_done
```

## 6. Ejecutar la primera ingesta

```bash
docker compose exec api python -m cip.ingest --query "complement system" --max-results 100
```

(O usa el atajo: `make ingest QUERY="complement system" N=100`)

Verás los logs de progreso. Tarda ~30-60 segundos para 100 papers.

## 7. Comprobar que funciona

### Healthcheck

```bash
curl http://localhost:8000/health
# {"status":"ok","version":"0.1.0"}
```

### Readiness con Postgres

```bash
curl http://localhost:8000/health/ready
# {"status":"ok","version":"0.1.0","database":"ok"}
```

### Listar los primeros papers

```bash
curl 'http://localhost:8000/papers?limit=3' | python -m json.tool
```

### Buscar por palabra clave

```bash
curl 'http://localhost:8000/papers/search?q=complement&limit=5' | python -m json.tool
```

### Swagger UI (interactivo)

Abre en el navegador: **http://localhost:8000/docs**

### Consola de MinIO (ver el XML crudo)

Abre **http://localhost:9001** — usuario `minioadmin`, password `minioadmin`.
En el bucket `pubmed-raw` verás los XML organizados por shard.
La API S3 de MinIO queda expuesta en el host en **http://localhost:9002**.

También puedes pedir la ubicación del XML crudo desde la API:

```bash
curl 'http://localhost:8000/papers/<PMID>/raw' | python -m json.tool
```

La respuesta incluye `pmid`, `s3_bucket`, `s3_key` y `presigned_url`.

### Consola de Postgres

```bash
docker compose exec postgres psql -U cip -d cip
```

Dentro:

```sql
SELECT count(*) FROM papers;
SELECT pmid, title, publication_year FROM papers LIMIT 5;
SELECT * FROM ingest_runs ORDER BY started_at DESC;
\q
```

## 8. Subir a GitHub

```bash
# Inicializar git si no lo está
cd clinical-intelligence-platform
git init
git add .
git commit -m "Sprint 1: PubMed ingestion + Postgres + MinIO + FastAPI"

# Crear el repo en GitHub
# Opción A — desde la web:
#   github.com/new -> nombre: clinical-intelligence-platform -> Create
#
# Opción B — con la CLI gh (más rápido):
#   brew install gh
#   gh auth login
#   gh repo create clinical-intelligence-platform --public --source=. --push

# Si fuiste por opción A:
git branch -M main
git remote add origin https://github.com/<TU_USUARIO>/clinical-intelligence-platform.git
git push -u origin main
```

**Importante:** asegúrate de que `.env` está en `.gitignore` (ya lo está) y de que **no subes tu API key**. Comprueba antes de hacer push:

```bash
git ls-files | grep -E '\.env$'   # debe estar vacío
```

## 9. Tests

```bash
docker compose exec api pytest -v
docker compose exec api ruff check src tests
docker compose exec api mypy src
```

Deberías ver los tests verdes y los checks sin errores.

## 10. Apagar

```bash
docker compose down          # mantiene los datos
docker compose down -v       # borra los volúmenes (Postgres + MinIO vacíos)
```

## Troubleshooting frecuente

| Síntoma | Causa | Solución |
|---|---|---|
| `port 5432 already in use` | Tienes un Postgres local corriendo | `brew services stop postgresql` o cambia el puerto en `docker-compose.yml` |
| `port 9000 already in use` | Otra app usa MinIO/Portainer | Cambia los puertos `9000:9000` y `9001:9001` |
| `connection refused` al ingest | API arrancó antes que Postgres | `docker compose restart api` o espera 10 s tras `up` |
| La ingesta se cuelga | Sin API key, rate limit duro | Pon una API key de PubMed en `.env` y reinicia: `docker compose restart api` |
| Logs muestran `403 Forbidden` de PubMed | Te identificaste mal | Revisa `PUBMED_EMAIL` en `.env` |

## Próximo paso

Cuando esto funcione y lo entiendas, abre `docs/ROADMAP.md` y empieza el Sprint 2.

**Recomendado:** instala **Claude Code** y desde la raíz del repo dile:

> "Lee README.md y docs/ROADMAP.md. Implementa el Sprint 2 sin tocar el código del Sprint 1, en una rama nueva `sprint-2-airflow`. Pregúntame antes de tomar decisiones de arquitectura."

Eso es lo que multiplica tu velocidad sin que pierdas el control.
