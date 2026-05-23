# Dashboard CEP — Paquímetro IoT

> Sistema IoT *event-driven* de baixo custo para digitalização da coleta de dados em postos de medição manual, com análise estatística de processo (CEP) em tempo real.
>
> **Trabalho de Conclusão de Curso** — Engenharia de Controle e Automação
> **Autor:** Hebert Emmanuel Rocha Peluso
> **Instituição:** IFMG — Campus Sabará

---

## Visão geral

Este repositório contém o código do *dashboard* de visualização do sistema descrito no TCC. O *dashboard* consome dados persistidos no Supabase e apresenta indicadores de Controle Estatístico de Processo (Cp, Cpk), gráfico de controle de Shewhart, histograma de distribuição e tabela de não conformidades.

A arquitetura completa do sistema é:

```
[Paquímetro + Potenciômetro] → [ESP32] → [HiveMQ Cloud (MQTT/TLS)]
                                                ↓
                                       [Ponte Python — local]
                                                ↓
                                       [Supabase — PostgreSQL]
                                                ↓
                                       [Dashboard Streamlit]
```

Este repositório hospeda **apenas o dashboard**. O *firmware* do ESP32 e a ponte MQTT→Supabase são executados separadamente (firmware no microcontrolador, ponte na máquina local do operador).

---

## Estrutura do repositório

```
.
├── supabase_dashboard.py    # Aplicação Streamlit principal
├── requirements.txt         # Dependências Python
├── .gitignore              # Arquivos não versionados (inclui secrets)
└── README.md               # Este arquivo
```

---

## Pré-requisitos

- Python 3.10+
- Conta no [Supabase](https://supabase.com) (plano gratuito é suficiente)
- Conta no [GitHub](https://github.com) (para deploy em nuvem)
- Conta no [Streamlit Community Cloud](https://streamlit.io/cloud) (gratuita, autenticada via GitHub)

---

## Configuração do Supabase

### 1. Criar projeto

1. Acesse [supabase.com](https://supabase.com) e crie uma conta (login com GitHub é o caminho mais rápido).
2. Clique em **New project**.
3. Defina nome, senha do banco (anote em local seguro) e região (preferencialmente **South America (São Paulo)** para menor latência).
4. Aguarde o provisionamento (~2 minutos).

### 2. Criar a tabela de medições

No painel do Supabase, acesse **SQL Editor** e execute:

```sql
-- Tabela principal de medições
CREATE TABLE leituras (
    id          BIGSERIAL PRIMARY KEY,
    valor_bruto INTEGER     NOT NULL,
    tensao      REAL        NOT NULL,
    medida_mm   REAL        NOT NULL,
    uptime_s    INTEGER     NOT NULL,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Índice para acelerar filtros por intervalo temporal
CREATE INDEX idx_leituras_timestamp ON leituras(timestamp);
```

### 3. Configurar Row Level Security (RLS)

O modelo de segurança separa **leitura** (dashboard público) de **escrita** (ponte local):

```sql
-- Habilita RLS na tabela
ALTER TABLE leituras ENABLE ROW LEVEL SECURITY;

-- Política 1: qualquer cliente com chave publicável pode LER
CREATE POLICY "leitura_publica" ON leituras
    FOR SELECT USING (true);

-- Política 2: apenas a service_role key pode ESCREVER
CREATE POLICY "escrita_service_role" ON leituras
    FOR INSERT TO service_role WITH CHECK (true);
```

> ⚠️ **Importante:** sem essas políticas, ou a tabela fica totalmente aberta (qualquer um pode escrever), ou completamente fechada (nem você consegue ler). As duas políticas juntas implementam o modelo de segurança documentado no Capítulo 5 do TCC.

### 4. Obter credenciais

Em **Settings → API Keys**, copie:

- **Project URL** (formato: `https://abcdefghijklmnop.supabase.co`) — usada em ambos os componentes
- **Publishable key** (formato: `sb_publishable_...`) — usada apenas pelo *dashboard*
- **Secret key** / **service_role key** (formato: `sb_secret_...` ou `eyJ...`) — usada apenas pela ponte local

| Componente | Onde executa | Chave | Permissões |
|------------|--------------|-------|------------|
| Ponte MQTT→Supabase | Máquina local | Service Role | Leitura + Escrita |
| Dashboard | Streamlit Cloud | Publishable | Apenas Leitura |

---

## Execução local (desenvolvimento)

### 1. Clonar o repositório

```bash
git clone https://github.com/hebertifmg-arch/tcc-dashboard-cep.git
cd tcc-dashboard-cep
```

### 2. Instalar dependências

Recomendado em ambiente virtual:

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Configurar credenciais locais

Crie o arquivo `.streamlit/secrets.toml` na raiz do projeto:

```toml
SUPABASE_URL = "https://seu-projeto.supabase.co"
SUPABASE_KEY = "sb_publishable_..."
```

> ⚠️ Esse arquivo está no `.gitignore` e **nunca** deve ser versionado.

### 4. Executar

```bash
streamlit run supabase_dashboard.py
```

O *dashboard* abre automaticamente em `http://localhost:8501`.

---

## Deploy em nuvem (Streamlit Community Cloud)

### 1. Tornar o repositório público no GitHub

O plano gratuito do Streamlit Cloud requer repositório público. Antes de publicar, **confirme que nenhuma credencial está versionada** — o arquivo `supabase_dashboard.py` deve conter apenas `st.secrets["SUPABASE_URL"]`, não a string hard-coded da URL/chave.

Em **Settings → General → Danger Zone → Change repository visibility**, escolha **Public**.

### 2. Conectar o Streamlit Cloud ao GitHub

1. Acesse [share.streamlit.io](https://share.streamlit.io) e faça login com a conta GitHub.
2. Autorize o Streamlit a acessar seus repositórios (apenas leitura).

### 3. Criar a aplicação

1. Clique em **New app**.
2. Preencha:
   - **Repository:** `hebertifmg-arch/tcc-dashboard-cep`
   - **Branch:** `main`
   - **Main file path:** `supabase_dashboard.py`
   - **App URL** (opcional): um identificador curto e memorável (ex: `hebert-tcc-cep`)
3. **Antes** de clicar em Deploy, expanda **Advanced settings → Secrets** e cole:

   ```toml
   SUPABASE_URL = "https://seu-projeto.supabase.co"
   SUPABASE_KEY = "sb_publishable_..."
   ```

   > Use **apenas** a *publishable key*. **Nunca** coloque a service_role aqui.

4. Clique em **Deploy**. O *build* leva ~2 minutos.

### 4. Validação

Acesse a URL pública (`https://seu-app.streamlit.app`) e verifique que o *dashboard* carrega sem mensagens de erro de credenciais. Se a tabela `leituras` ainda estiver vazia, a interface exibe um aviso solicitando a execução da ponte.

---

## Manutenção e atualização

### Atualizar o código

Qualquer `push` para o *branch* `main` dispara um *redeploy* automático no Streamlit Cloud (leva ~30 segundos). Não é necessário ação manual.

### Atualizar dependências

Para adicionar uma biblioteca, edite `requirements.txt` e faça *commit*. O Streamlit Cloud reconstrói o ambiente automaticamente no próximo *deploy*.

### Monitorar uso

- **Supabase:** Dashboard do Supabase → **Reports** → uso de Database e Bandwidth.
- **Streamlit:** [share.streamlit.io](https://share.streamlit.io) → **Manage app** → logs em tempo real.

### Limites do plano gratuito

| Serviço | Limite | Suficiente para |
|---------|--------|-----------------|
| Supabase | 500 MB de banco, 5 GB de *bandwidth*/mês, API ilimitada | ~100 milhões de medições |
| Streamlit Cloud | 1 GB RAM, aplicação hiberna após dias sem uso | Demonstrações, TCC, baixo tráfego |

---

## Solução de problemas

### "Credencial faltando: SUPABASE_URL"
Os *secrets* não estão configurados. Verifique:
- **Local:** existe o arquivo `.streamlit/secrets.toml` com as duas chaves?
- **Cloud:** em **Settings → Secrets**, as duas variáveis estão presentes e com aspas duplas?

### "new row violates row-level security policy"
A ponte está usando a chave errada (publishable em vez da service_role). A publishable só tem permissão de leitura — para escrita é necessário usar a service_role.

### Erro `getaddrinfo failed`
Problema de conexão DNS. Verifique se a `SUPABASE_URL` está completa (com `https://` no início e `.supabase.co` no fim) e que o projeto Supabase não está pausado.

### O *dashboard* não atualiza automaticamente
O cache do Streamlit tem TTL de 10 segundos. Use o botão **Atualizar agora** na barra lateral, ou habilite o **Auto-refresh (10s)**.

### Cota de leituras excedida (Firebase)
Sintoma do projeto descontinuado. Este sistema migrou para Supabase justamente por esse motivo — consulte a Seção 5.2 do TCC para detalhes da decisão arquitetural.

---

## Componentes relacionados (não versionados aqui)

- **Firmware do ESP32:** disponível no Apêndice A do TCC.
- **Ponte MQTT → Supabase:** *script* `ponte_mqtt_supabase.py` executado localmente. Contém a *service_role key* e por isso **nunca** é versionado em repositório público.

---

## Licença

Código distribuído sob licença MIT para fins acadêmicos. As bibliotecas de terceiros mantêm suas respectivas licenças originais.

---

## Contato

Hebert Emmanuel Rocha Peluso — [hebertifmg@gmail.com](mailto:hebertifmg@gmail.com)

Repositório do projeto: [github.com/hebertifmg-arch/tcc-dashboard-cep](https://github.com/hebertifmg-arch/tcc-dashboard-cep)
