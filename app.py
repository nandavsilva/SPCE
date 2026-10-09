from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs
import html
import sqlite3


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "estudos.db"
STATIC_DIR = BASE_DIR / "static"


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_database():
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                goal TEXT NOT NULL DEFAULT ''
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS study_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER NOT NULL,
                studied_on TEXT NOT NULL,
                minutes INTEGER NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (subject_id) REFERENCES subjects(id)
            )
            """
        )


def fetch_dashboard_data():
    with get_connection() as connection:
        subjects = connection.execute(
            """
            SELECT
                subjects.id,
                subjects.name,
                subjects.goal,
                COALESCE(SUM(study_sessions.minutes), 0) AS total_minutes,
                COUNT(study_sessions.id) AS session_count
            FROM subjects
            LEFT JOIN study_sessions ON study_sessions.subject_id = subjects.id
            GROUP BY subjects.id
            ORDER BY subjects.name
            """
        ).fetchall()
        sessions = connection.execute(
            """
            SELECT
                study_sessions.studied_on,
                study_sessions.minutes,
                study_sessions.notes,
                subjects.name AS subject_name
            FROM study_sessions
            JOIN subjects ON subjects.id = study_sessions.subject_id
            ORDER BY study_sessions.studied_on DESC, study_sessions.id DESC
            LIMIT 8
            """
        ).fetchall()
    return subjects, sessions


def escape(value):
    return html.escape(str(value), quote=True)


def render_page(title, body):
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escape(title)} | Planejador de Estudos</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <header class="topbar">
        <div>
            <p class="eyebrow">SPCE</p>
            <h1>Planejador de Estudos</h1>
        </div>
        <nav>
            <a href="/">Painel</a>
            <a href="/nova-materia">Nova materia</a>
            <a href="/nova-sessao">Registrar estudo</a>
        </nav>
    </header>
    <main>
        {body}
    </main>
</body>
</html>"""


def render_dashboard():
    subjects, sessions = fetch_dashboard_data()
    total_minutes = sum(row["total_minutes"] for row in subjects)
    total_sessions = sum(row["session_count"] for row in subjects)

    subject_cards = "\n".join(
        f"""
        <article class="card">
            <div>
                <h3>{escape(subject["name"])}</h3>
                <p>{escape(subject["goal"]) or "Sem meta cadastrada."}</p>
            </div>
            <strong>{subject["total_minutes"]} min</strong>
            <span>{subject["session_count"]} sessoes</span>
        </article>
        """
        for subject in subjects
    )
    if not subject_cards:
        subject_cards = """
        <article class="empty-state">
            <h3>Nenhuma materia cadastrada ainda</h3>
            <p>Comece criando uma materia e depois registre suas sessoes de estudo.</p>
            <a class="button" href="/nova-materia">Criar primeira materia</a>
        </article>
        """

    session_rows = "\n".join(
        f"""
        <tr>
            <td>{escape(session["studied_on"])}</td>
            <td>{escape(session["subject_name"])}</td>
            <td>{session["minutes"]} min</td>
            <td>{escape(session["notes"])}</td>
        </tr>
        """
        for session in sessions
    )
    if not session_rows:
        session_rows = """
        <tr>
            <td colspan="4">Nenhum estudo registrado ainda.</td>
        </tr>
        """

    body = f"""
    <section class="summary">
        <article>
            <span>Total estudado</span>
            <strong>{total_minutes} min</strong>
        </article>
        <article>
            <span>Sessoes registradas</span>
            <strong>{total_sessions}</strong>
        </article>
        <article>
            <span>Materias</span>
            <strong>{len(subjects)}</strong>
        </article>
    </section>

    <section class="section-header">
        <h2>Materias</h2>
        <a class="button" href="/nova-materia">Adicionar</a>
    </section>
    <section class="grid">
        {subject_cards}
    </section>

    <section class="section-header">
        <h2>Ultimas sessoes</h2>
        <a class="button secondary" href="/nova-sessao">Registrar</a>
    </section>
    <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th>Data</th>
                    <th>Materia</th>
                    <th>Tempo</th>
                    <th>Anotacoes</th>
                </tr>
            </thead>
            <tbody>{session_rows}</tbody>
        </table>
    </div>
    """
    return render_page("Painel", body)


def render_subject_form(error=""):
    error_html = f'<p class="error">{escape(error)}</p>' if error else ""
    body = f"""
    <section class="form-panel">
        <h2>Nova materia</h2>
        {error_html}
        <form method="post" action="/nova-materia">
            <label>
                Nome da materia
                <input name="name" required placeholder="Ex.: Matematica">
            </label>
            <label>
                Meta
                <textarea name="goal" rows="4" placeholder="Ex.: Resolver 30 exercicios por semana"></textarea>
            </label>
            <button type="submit">Salvar materia</button>
        </form>
    </section>
    """
    return render_page("Nova materia", body)


def render_session_form(error=""):
    subjects, _ = fetch_dashboard_data()
    options = "\n".join(
        f'<option value="{subject["id"]}">{escape(subject["name"])}</option>'
        for subject in subjects
    )
    if not options:
        body = """
        <section class="empty-state">
            <h2>Cadastre uma materia primeiro</h2>
            <p>Voce precisa de pelo menos uma materia antes de registrar uma sessao.</p>
            <a class="button" href="/nova-materia">Criar materia</a>
        </section>
        """
        return render_page("Registrar estudo", body)

    error_html = f'<p class="error">{escape(error)}</p>' if error else ""
    body = f"""
    <section class="form-panel">
        <h2>Registrar estudo</h2>
        {error_html}
        <form method="post" action="/nova-sessao">
            <label>
                Materia
                <select name="subject_id" required>{options}</select>
            </label>
            <label>
                Data
                <input type="date" name="studied_on" required>
            </label>
            <label>
                Minutos estudados
                <input type="number" name="minutes" min="1" required placeholder="45">
            </label>
            <label>
                Anotacoes
                <textarea name="notes" rows="4" placeholder="O que voce estudou hoje?"></textarea>
            </label>
            <button type="submit">Salvar sessao</button>
        </form>
    </section>
    """
    return render_page("Registrar estudo", body)


def redirect_to_home(handler):
    handler.send_response(303)
    handler.send_header("Location", "/")
    handler.end_headers()


def read_form(handler):
    length = int(handler.headers.get("Content-Length", 0))
    raw_body = handler.rfile.read(length).decode("utf-8")
    return {key: values[0].strip() for key, values in parse_qs(raw_body).items()}


class StudyPlannerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.respond_html(render_dashboard())
        elif self.path == "/nova-materia":
            self.respond_html(render_subject_form())
        elif self.path == "/nova-sessao":
            self.respond_html(render_session_form())
        elif self.path == "/static/style.css":
            self.respond_static("style.css", "text/css; charset=utf-8")
        else:
            self.send_error(404, "Pagina nao encontrada")

    def do_POST(self):
        if self.path == "/nova-materia":
            self.create_subject()
        elif self.path == "/nova-sessao":
            self.create_session()
        else:
            self.send_error(404, "Pagina nao encontrada")

    def create_subject(self):
        form = read_form(self)
        name = form.get("name", "")
        goal = form.get("goal", "")
        if not name:
            self.respond_html(render_subject_form("Informe o nome da materia."))
            return

        with get_connection() as connection:
            connection.execute(
                "INSERT INTO subjects (name, goal) VALUES (?, ?)",
                (name, goal),
            )
        redirect_to_home(self)

    def create_session(self):
        form = read_form(self)
        subject_id = form.get("subject_id", "")
        studied_on = form.get("studied_on", "")
        minutes = form.get("minutes", "")
        notes = form.get("notes", "")

        if not subject_id or not studied_on or not minutes:
            self.respond_html(render_session_form("Preencha materia, data e minutos."))
            return

        try:
            minutes_value = int(minutes)
        except ValueError:
            self.respond_html(render_session_form("Minutos precisa ser um numero."))
            return

        if minutes_value <= 0:
            self.respond_html(render_session_form("Minutos precisa ser maior que zero."))
            return

        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO study_sessions (subject_id, studied_on, minutes, notes)
                VALUES (?, ?, ?, ?)
                """,
                (subject_id, studied_on, minutes_value, notes),
            )
        redirect_to_home(self)

    def respond_html(self, html_text):
        encoded = html_text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def respond_static(self, filename, content_type):
        path = STATIC_DIR / filename
        if not path.exists():
            self.send_error(404, "Arquivo nao encontrado")
            return

        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def main():
    init_database()
    server = ThreadingHTTPServer(("127.0.0.1", 8000), StudyPlannerHandler)
    print("Servidor rodando em http://127.0.0.1:8000")
    print("Pressione Ctrl+C para parar.")
    server.serve_forever()


if __name__ == "__main__":
    main()
