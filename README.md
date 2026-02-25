# Flask Knowledge Management & Chat Application

A powerful knowledge management and chat application built with Flask, integrating Google's Gemini AI for varied response modes (basic, research, analytical, expert). The application supports project management, document visualization, and cross-project analysis.

## 🚀 Features

### 🔐 Authentication & User Management
- **Secure Login**: Access restricted to `@adventz.com` email addresses.
- **Role-Based Access**: Admin and User roles.
- **Rate Limiting**: Protects against brute-force attacks.
- **Session Management**: Secure session handling with CSRF protection.

### 📋 Admin Dashboard
- **Project Management**: Create, edit, and delete projects.
- **Metadata Management**: Upload and manage project PDF documents.
- **Dependency Management**: Define relationships between projects for cross-project analysis.
- **User Management**: Manage user roles and accounts.
- **Audit Logs**: Track user activities and security events.

### 💬 Intelligent Chat
- **Gemini Integration**: Utilizes Google's Gemini AI for generating responses.
- **Multiple Modes**:
  - **Basic**: Initial response.
  - **Research**: In-depth information gathering.
  - **Analytical**: Detailed analysis.
  - **Expert**: High-level expert opinion.
  - **Cross-Project**: Analyzes dependencies for broader context.
  - **Comparison**: Compares uploaded documents against project knowledge.
- **Streaming Responses**: Real-time answer generation.
- **Chat History**: Save and pin important sessions.

### 🖼️ Visualization & Files
- **3D Visualization**: Interactive 3D view of the DAP plant (Process Flow).
- **Document Viewer**: Securely view PDF documents within the application.
- **File Security**: Path validation to prevent unauthorized file access.

## 🛠️ Tech Stack

- **Backend**: Flask 3.0
- **Database**: MySQL (via PyMySQL & SQLAlchemy)
- **AI/LLM**: Google Gemini (google-genai)
- **Frontend**: HTML5, JavaScript (Vanilla), Jinja2 Templates
- **PDF Processing**: PyMuPDF (fitz)
- **Security**: Flask-Login, Flask-WTF (CSRF), Flask-Limiter, Bleach

## ⚙️ Prerequisites

- Python 3.8+
- MySQL Server
- Google Gemini API Key

## 📦 Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd Flask
    ```

2.  **Create a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables:**
    Create a `.env` file in the root directory and add the following (adjust values as needed):
    ```env
    FLASK_APP=app.py
    FLASK_ENV=development
    SECRET_KEY=your_strong_secret_key
    SQLALCHEMY_DATABASE_URI=mysql+pymysql://user:password@localhost/db_name
    GEMINI_API_KEY=your_gemini_api_key

    # Local document and metadata directories (used when S3 toggle is off)
    PROJECT_DOCS_DIR=path/to/project_docs
    PROCESS_METADATA_DIR=path/to/process_metadata

    # Project document storage toggle (local vs S3)
    USE_S3_FOR_PROJECT_DOCS=False
    AWS_ACCESS_KEY_ID=your_aws_access_key_id
    AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key
    AWS_REGION=your_aws_region
    S3_PROJECT_DOCS_BUCKET=your_s3_bucket_name
    # Optional prefix inside the bucket where project documents are stored
    S3_PROJECT_DOCS_PREFIX=project-docs

    # Admin user credentials (used by db_init.py)
    ADMIN_EMAIL=admin@adventz.com
    ADMIN_PASSWORD=change_this_in_production
    ```

## 🗄️ Database Setup

The application includes a script to initialize the database and seed initial data.

1.  **Run the initialization script:**
    ```bash
    python db_init.py
    ```
    This will:
    - Create necessary database tables.
    - Create (or update) the admin user using credentials from your `.env` file:
        - **Email**: `ADMIN_EMAIL` (default `admin@adventz.com` if not set)
        - **Password**: `ADMIN_PASSWORD` (default `admin123` if not set; **you must change this for production**)
    - Seed core projects (DAP, SAP, PAP, AMMONIA).
    - Load metadata from CSVs if available.

## 🚀 Usage

1.  **Run the application:**
    ```bash
    python app.py
    ```
    The app will start at `http://localhost:5000`.

2.  **Login:**
    Use `admin@adventz.com` / `admin123` to log in as an administrator.

3.  **Admin Panel:**
    Navigate to `/admin` to manage projects, users, and files.

4.  **User Dashboard:**
    Access project documents, view visualizations, and start chat sessions from the main dashboard.

## 📂 Project Structure

```
Flask/
├── app.py                 # Application entry point
├── config.py              # Configuration settings
├── extensions.py          # Flask extensions (DB, Login, CSRF, etc.)
├── db_init.py             # Database initialization script
├── requirements.txt       # Project dependencies
├── routes/                # Blueprint definitions
│   ├── admin.py           # Admin routes
│   ├── auth.py            # Authentication routes
│   └── main.py            # Main application routes
├── models/                # Database models
│   ├── user.py
│   ├── project.py
│   ├── audit.py
│   └── conversation.py
├── services/              # Business logic
│   └── qna_service.py     # Gemini AI integration service
├── templates/             # HTML Templates
└── static/                # Static assets (CSS, JS, Images)
```

## 🛡️ Security Note
This application enforces strict email domain restrictions (`@adventz.com`) for registration and login. Ensure your users have the appropriate email addresses.
