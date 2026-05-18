from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
import requests  # <-- Necesario para hablar con OpenRouter

app = Flask(__name__)
app.secret_key = 'novasalut_secret_key_2026'

# --- CONEXIÓN A AMAZON AURORA ---
DB_USER = 'admin'
DB_PASS = 'Passw0rd!:.'
DB_HOST = 'auroracluster.cluster-ccvsi5zk9s0d.us-east-1.rds.amazonaws.com'
DB_NAME = 'triplejota_db'

app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- CONFIGURACIÓN DE OPENROUTER ---
# Reemplaza esto con tu API Key real de OpenRouter
OPENROUTER_API_KEY = "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"
# Puedes cambiar el modelo. Este es uno gratuito y muy bueno de Llama 3:
AI_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free" 


# --- MODELOS DE DATOS ---
class Paciente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    dni = db.Column(db.String(20), unique=True, nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(200), nullable=False)
    citas = db.relationship('Cita', backref='paciente', lazy=True)

class Cita(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.String(20), nullable=False)
    horario = db.Column(db.String(20), nullable=False)
    especialidad = db.Column(db.String(50), nullable=False)
    medico = db.Column(db.String(100), nullable=False)
    observaciones = db.Column(db.String(250))
    paciente_id = db.Column(db.Integer, db.ForeignKey('paciente.id'), nullable=False)

# --- INICIALIZACIÓN ---
with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        print(f"Error inicializando DB: {e}")

# --- RUTAS DE NAVEGACIÓN ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        dni_f = request.form.get('dni')
        nombre_f = request.form.get('nombre')
        pass_f = request.form.get('password')

        existe = Paciente.query.filter_by(dni=dni_f).first()
        if existe:
            flash('El DNI ya está registrado.', 'danger')
            return redirect(url_for('register'))

        nuevo_paciente = Paciente(dni=dni_f, nombre=nombre_f, password=pass_f)
        try:
            db.session.add(nuevo_paciente)
            db.session.commit()
            flash('Cuenta creada. Ya puedes iniciar sesión.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('Error al crear la cuenta.', 'danger')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        dni_f = request.form.get('dni')
        pass_f = request.form.get('password')
        user = Paciente.query.filter_by(dni=dni_f).first()
        if user and user.password == pass_f:
            session['user_id'] = user.id
            session['user_name'] = user.nombre
            flash(f'Bienvenido, {user.nombre}', 'success')
            return redirect(url_for('home'))
        else:
            flash('DNI o contraseña incorrectos.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/citas', methods=['GET', 'POST'])
def citas():
    if 'user_id' not in session:
        flash('Inicie sesión primero.', 'warning')
        return redirect(url_for('login'))
    if request.method == 'POST':
        try:
            nueva_cita = Cita(
                fecha=request.form.get('fecha'),
                horario=request.form.get('horario'),
                especialidad=request.form.get('especialidad'),
                medico=request.form.get('medico'),
                observaciones=request.form.get('observaciones'),
                paciente_id=session['user_id']
            )
            db.session.add(nueva_cita)
            db.session.commit()
            flash('✅ Cita guardada.', 'success')
            return redirect(url_for('historial'))
        except Exception as e:
            db.session.rollback()
            flash('❌ Error al guardar.', 'danger')
    return render_template('citas.html')

@app.route('/historial')
def historial():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    mis_citas = Cita.query.filter_by(paciente_id=session['user_id']).all()
    return render_template('historial.html', citas=mis_citas)

@app.route('/chat', methods=['POST'])
def chat():
    try:
        # 1. Obtener mensaje
        data = request.json
        user_message = data.get('message')
        if not user_message:
            return jsonify({"response": "No se recibió ningún mensaje."})
        
        # 2. Definir personalidad base
        system_prompt = "Eres el asistente médico virtual del 'Centro de Salud Digital'. Eres amable, profesional y conciso."
        
        # 3. Leer de Aurora (con comprobación de seguridad)
        if 'user_id' in session:
            user = Paciente.query.get(session['user_id'])
            if user:
                system_prompt += f" Estás hablando con el paciente registrado llamado {user.nombre}."
                citas = Cita.query.filter_by(paciente_id=user.id).all()
                if citas:
                    lista_citas = ", ".join([f"{c.fecha} a las {c.horario} con el Dr. {c.medico} ({c.especialidad})" for c in citas])
                    system_prompt += f" El paciente tiene estas citas médicas: {lista_citas}."
                else:
                    system_prompt += " El paciente no tiene citas programadas actualmente."
        else:
            system_prompt += " Estás hablando con un usuario no registrado. Invítale a iniciar sesión para ver sus citas."

        # 4. Preparar llamada a OpenRouter
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost", # Importante para OpenRouter
            "X-Title": "Centro de Salud Digital"
        }
        
        payload = {
            "model": AI_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
        }
        
        # 5. Petición real
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions", 
            headers=headers, 
            json=payload, 
            timeout=15
        )
        
        # --- COMPROBACIÓN DE ERRORES DE LA API ---
        if response.status_code != 200:
            print(f"ERROR OPENROUTER: {response.status_code} - {response.text}")
            return jsonify({"response": f"Error de la IA (Código {response.status_code}). Revisa tu API Key y saldo en OpenRouter."})

        response_data = response.json()
        
        # 6. Extraer respuesta de forma segura
        if 'choices' in response_data and len(response_data['choices']) > 0:
            respuesta_final = response_data['choices'][0]['message']['content']
        else:
            respuesta_final = "La IA conectó correctamente pero no devolvió una respuesta válida."

        return jsonify({"response": respuesta_final})

    except Exception as e:
        # Este print aparecerá en tu terminal (journalctl)
        print(f"DEBUG: Error crítico en /chat: {str(e)}")
        # Este mensaje aparecerá en el chat del navegador
        return jsonify({"response": f"Error interno del servidor: {str(e)}"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
