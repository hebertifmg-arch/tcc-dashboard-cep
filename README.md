# Dashboard CEP - Paquímetro IoT

Dashboard de Controle Estatístico de Processo para o TCC de Hebert Peluso (IFMG Sabará).

Pipeline: ESP32 → HiveMQ Cloud → ponte Python → Supabase (PostgreSQL) → Dashboard Streamlit.

## Rodar localmente

1. Clone o repositório
2. Instale dependências: `pip install -r requirements.txt`
3. Crie `.streamlit/secrets.toml` baseado em `secrets.toml.example`
4. Rode: `streamlit run supabase_dashboard.py`

## Deploy

Hospedado no Streamlit Community Cloud. Credenciais configuradas via Secrets do painel.
