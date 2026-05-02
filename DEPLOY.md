# Deploy Jeeves to free services

## Architecture (free tier)

| Service | What | Why |
|---------|------|-----|
| **Render** | FastAPI container | Free web service (750 hrs/mo) |
| **Neon.tech** | PostgreSQL | Free, permanent, 512MB |
| **Upstash** | Redis (optional) | Free, 10k cmds/day |
| **Local disk** | ChromaDB + knowledge | PersistentClient on Render's disk |

## 1. Create Neon PostgreSQL

1. Go to https://neon.tech → Sign up (GitHub)
2. Create project → get connection string like:
   `postgresql://user:pass@ep-xyz.us-east-2.aws.neon.tech/dbname?sslmode=require`
3. Copy it

## 2. Create Upstash Redis (optional)

1. Go to https://upstash.com → Sign up
2. Create database → copy the **REST URL** or **REDIS_URL**
3. If you skip this, conversation memory will be in-memory (lost on restart)

## 3. Deploy to Render

1. Push your code to **GitHub** (private repo is fine)
2. Go to https://render.com → Sign up (GitHub)
3. **New → Web Service**
4. Connect your repo
5. Settings:
   - **Name**: `jeeves`
   - **Region**: Frankfurt (closest to you)
   - **Branch**: `main`
   - **Root Directory**: `api`
   - **Runtime**: `Docker`
   - **Dockerfile**: `Dockerfile`
   - **Plan**: **Free**

6. Add **Environment Variables**:

| Key | Value |
|-----|-------|
| `DATABASE_URL` | `postgresql+psycopg2://` + your Neon URL |
| `REDIS_URL` | Upstash URL (or leave empty) |
| `CHROMA_PATH` | `/opt/data/chroma` |
| `KNOWLEDGE_DIR` | `/opt/data/knowledge` |
| `OPENAI_API_KEY` | `sk-...` |
| `JWT_SECRET` | any random string (min 32 chars) |
| `PUBLIC_BASE_URL` | will auto-set after deploy |

7. Click **Create Web Service**

8. After deploy, copy the URL (e.g. `https://jeeves-xyz.onrender.com`)

9. Go back to Environment Variables → set `PUBLIC_BASE_URL` to that URL → Save & Redeploy

## 4. Connect Telegram

1. In Jeeves admin → Channels → Telegram
2. Enter bot token
3. Webhook URL = `https://jeeves-xyz.onrender.com/channels/telegram/webhook`
4. Save & Test → should show ✅

## Notes

- **Free Render sleeps after 15 min** of inactivity → first request takes ~30s to wake up
- Telegram webhook will queue messages — they'll be processed when Render wakes up
- For production reliability, upgrade to Render Starter ($7/mo)
- Chroma data persists across deploys (stored on Render's persistent disk)
