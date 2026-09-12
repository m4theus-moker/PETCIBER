# 🐾 PetCiber

Plataforma web para tutores acompanharem a saúde e a rotina de seus pets em tempo real — sinais vitais simulados por sensores, agenda de eventos com lembretes automáticos, chatbot de suporte e uma pequena loja integrada.

> Projeto pessoal desenvolvido para aplicar, na prática, conceitos de backend web, tempo real e persistência de dados.

---

## ✨ Funcionalidades

- **Autenticação de usuários** — cadastro e login com senhas armazenadas via hash (Werkzeug), sessões protegidas por login obrigatório nas rotas internas.
- **Cadastro de pets** — nome, raça, histórico e foto, vinculados ao tutor logado.
- **Monitoramento em tempo real** — painel com BPM e temperatura via WebSockets (Flask-SocketIO), atualizado ao vivo sem precisar recarregar a página.
- **Análise automática de estado do pet** — regras que cruzam batimentos, temperatura corporal/ambiente e nível de atividade para gerar alertas (ex: taquicardia, febre, hipotermia) e sugestões.
- **Ingestão de dados de sensores via API** — endpoint protegido por API Key para dispositivos externos (ex: um ESP32/Arduino) enviarem leituras de BPM/temperatura.
- **Agenda inteligente** — cadastro de eventos (vacinas, consultas) com lembretes automáticos por e-mail e notificação push (Web Push/VAPID) no dia do evento.
- **Chatbot de suporte** — assistente por comandos (`/status`, `/eventos`, `/checklist`, `/racao`, `/asfalto`) que consulta o banco e responde sobre o pet do tutor.
- **Radar de temperatura do asfalto** — estimativa de risco para os pets em dias quentes.
- **Loja integrada** — catálogo de produtos, carrinho de compras e checkout com cupom de desconto.
- **Painel de histórico** — gráficos de BPM e temperatura ao longo do tempo (Chart.js).

## 🛠️ Tecnologias

**Backend**
- Python 3
- Flask
- Flask-SocketIO (comunicação em tempo real)
- Flask-Limiter (rate limiting)
- Werkzeug Security (hash de senha)
- SQLite3 (persistência de dados)
- APScheduler *(opcional — agendamento de tarefas em background)*
- pywebpush *(opcional — notificações push)*

**Frontend**
- Jinja2 (templates renderizados no servidor)
- Chart.js (gráficos em tempo real)
- Socket.IO client

**Infraestrutura / Integrações**
- SMTP (envio de e-mails de lembrete)
- Web Push API (VAPID)

## 📁 Estrutura do projeto

```
petciber/
├── app.py                  # Aplicação Flask principal (rotas, models, regras de negócio)
├── templates/               # Páginas HTML (Jinja2)
├── static/
│   ├── uploads/              # Uploads de usuários (carteirinhas, fotos)
│   └── brand/                 # Logo e identidade visual
├── petciber.db              # Banco SQLite (gerado automaticamente, não versionado)
├── .env.example              # Modelo de variáveis de ambiente
├── .gitignore
└── README.md
```

## 🗄️ Modelo de dados

| Tabela         | Descrição                                              |
|----------------|---------------------------------------------------------|
| `usuarios`     | Tutores cadastrados (nome, e-mail, senha com hash, telefone) |
| `pets`         | Pets vinculados a um tutor, com raça, histórico e foto  |
| `vitais`       | Histórico de leituras de BPM e temperatura por pet      |
| `eventos_pet`  | Eventos da agenda (vacinas, consultas) com controle de notificação |
| `devices`      | Dispositivos de sensor vinculados a um pet              |
| `push_subs`    | Inscrições de notificação push por usuário              |
| `orders`       | Pedidos feitos na loja integrada                        |

## 🚀 Como rodar localmente

### Pré-requisitos
- Python 3.10+
- pip

### 1. Clone o repositório
```bash
git clone https://github.com/m4theus-moker/petciber.git
cd petciber
```

### 2. Crie e ative um ambiente virtual
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

### 3. Instale as dependências
```bash
pip install flask flask-socketio flask-limiter werkzeug requests apscheduler pywebpush
```

### 4. Configure as variáveis de ambiente
Copie o arquivo de exemplo e preencha com seus próprios valores (nunca use os valores de exemplo em produção):
```bash
cp .env.example .env
```

Variáveis disponíveis:

| Variável              | Obrigatória | Descrição                                         |
|-----------------------|:-----------:|----------------------------------------------------|
| `SECRET_KEY`          | ✅          | Chave secreta do Flask (sessões)                   |
| `API_KEY`             | ✅          | Chave para autenticar a ingestão de dados de sensores |
| `DB_PATH`             | ❌          | Caminho do banco SQLite (padrão: `petciber.db`)     |
| `SITE_BASE_URL`       | ❌          | URL base usada em links de e-mail/notificação       |
| `SMTP_HOST/PORT/USER/PASS` | ❌     | Configuração de envio de e-mail (lembretes)         |
| `MAIL_FROM`           | ❌          | Remetente dos e-mails                               |
| `VAPID_PUBLIC_KEY`    | ❌          | Chave pública para notificações push                |
| `VAPID_PRIVATE_KEY`   | ❌          | Chave privada para notificações push                |
| `VAPID_CLAIMS`        | ❌          | E-mail de contato exigido pelo protocolo VAPID      |

> ⚠️ Nunca commite o arquivo `.env` com valores reais. Gere chaves novas para `SECRET_KEY`, `API_KEY` e o par VAPID antes de rodar em produção.

### 5. Execute a aplicação
```bash
python app.py
```
O servidor sobe automaticamente em uma porta livre a partir de `5001` e exibe o endereço no terminal.

### Rota de demonstração
Acesse `/debug/seed` para criar um usuário de teste (`demo@petciber.com`) com um pet de exemplo já cadastrado.

## 🔒 Notas de segurança

Este é um projeto de estudo, então algumas escolhas priorizam simplicidade sobre robustez de produção:
- As chaves têm valores padrão no código (`chave_secreta_segura`, `PETCIBER123`) caso as variáveis de ambiente não sejam definidas — **sempre defina as suas** antes de expor o app publicamente.
- Os dados de sensores (BPM/temperatura) exibidos no dashboard são simulados para fins de demonstração.

## 🗺️ Possíveis melhorias futuras
- Migrar de SQLite para PostgreSQL em ambiente de produção
- Adicionar testes automatizados
- Substituir o carregamento manual de variáveis de ambiente por `python-dotenv`
- Dockerizar a aplicação

## 👤 Autor

**Matheus Mota Alves Dias**
Estudante de Ciência da Computação | Técnico em Inteligência Artificial (FECAP)
[GitHub](https://github.com/m4theus-moker)
