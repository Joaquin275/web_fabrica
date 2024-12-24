from flask import Flask, render_template, request, session, redirect, url_for, send_file
import pandas as pd
import os
import matplotlib.pyplot as plt
import io
import base64
from flask_mail import Mail, Message
import unicodedata
from datetime import datetime, timedelta
from reportlab.pdfgen import canvas
import tempfile


app = Flask(__name__)
app.secret_key = 'secret_key'

# Configuración del servidor de correo
app.config['MAIL_SERVER'] = 'smtp.office365.com'  # Servidor corporativo
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False  # Asegúrate de que SSL esté deshabilitado si estás usando TLS
app.config['MAIL_USERNAME'] = 'joaquingonzalez@higoma.es'  # Correo de envío
app.config['MAIL_PASSWORD'] = 'H/057141400422ub'  # Contraseña del correo
mail = Mail(app)

# Función para cargar clientes desde Excel
def cargar_clientes():
    ruta_archivo = r"C:\Users\Joaqu\OneDrive\Desktop\web_fabrica\templates\Clientes.xlsx"
    if os.path.exists(ruta_archivo):
        return pd.read_excel(ruta_archivo, engine="openpyxl")
    else:
        print("Error: El archivo Clientes.xlsx no se encuentra.")
        return pd.DataFrame(columns=["Correo electronico", "Nombre Completo", "Telefono", "Dirección de envio", "Empresa"])
    
    # Función para cargar platos desde el archivo Excel
def cargar_platos():
    ruta_archivo = r"C:\Users\Joaqu\OneDrive\Desktop\web_fabrica\templates\platos.xlsx"
    if os.path.exists(ruta_archivo):
        return pd.read_excel(ruta_archivo, engine="openpyxl")
    return pd.DataFrame(columns=["Nombre"])

# Función para cargar el menú semanal desde un archivo Excel
def cargar_menu_semanal():
    ruta_archivo = "menu_semanal.xlsx"
    if os.path.exists(ruta_archivo):
        menu = pd.read_excel(ruta_archivo, sheet_name=None, engine="openpyxl")
        return {sheet_name: menu[sheet_name]['Plato'].tolist() for sheet_name in menu.keys()}
    return {dia: [] for dia in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]}

# Función para guardar el menú semanal en un archivo Excel
def guardar_menu_semanal(menu):
    with pd.ExcelWriter("menu_semanal.xlsx", engine="openpyxl") as writer:
        for dia, platos in menu.items():
            pd.DataFrame({"Plato": platos}).to_excel(writer, sheet_name=dia, index=False)

    

# Función para limpiar caracteres especiales
def clean_text(input_str):
    return unicodedata.normalize('NFKD', input_str).encode('ascii', 'ignore').decode('utf-8')

# Función para enviar correos
def enviar_correo(destinatario, asunto, mensaje):
    msg = Message(subject=asunto, recipients=[destinatario], body=mensaje)
    try:
        mail.send(msg)
        print(f"Correo enviado a {destinatario}")
    except Exception as e:
        print(f"Error enviando correo a {destinatario}: {e}")
#Menu semanal
menu_semanal = {
    "Lunes": [],
    "Martes": [],
    "Miércoles": [],
    "Jueves": [],
    "Viernes": []
}




# Credenciales del administrador
ADMIN_CREDENTIALS = {
    "email": "admin@example.com",  # Cambia este correo al del administrador
    "password": "admin123"         # Cambia esta contraseña al del administrador
}

# Ruta principal: Login
@app.route('/', methods=['GET', 'POST'])
def login():
    clientes = cargar_clientes()
    if 'user' in session:
        if session.get('is_admin'):
            return redirect(url_for('admin'))  # Redirige al panel de administrador si es admin
        return redirect(url_for('menu_route'))  # Redirige al menú si es usuario regular

    if request.method == 'POST':
        email = request.form.get("email").strip().lower()
        password = request.form.get("password")  # Puede ser None si no se ingresa contraseña

        # Verificar si es administrador
        if email == ADMIN_CREDENTIALS["email"]:
            # Verificar contraseña del administrador
            if password == ADMIN_CREDENTIALS["password"]:
                session['user'] = email
                session['is_admin'] = True
                return redirect(url_for('admin'))
            else:
                return render_template('login.html', error="Contraseña incorrecta para administrador.")

        # Verificar si es un usuario regular
        cliente = clientes[clientes['Correo electronico'] == email]
        if not cliente.empty:
            session['user'] = email
            session['datos_cliente'] = cliente.iloc[0].to_dict()
            session['is_admin'] = False
            return redirect(url_for('menu_route'))
        else:
            return render_template('login.html', error="Correo no autorizado o no encontrado.")

    return render_template('login.html')

# Ruta de administrador
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    # Verificar si el usuario es administrador
    if 'user' not in session or not session.get('is_admin'):
        return redirect(url_for('login'))

    # Cargar el archivo de pedidos
    archivo_excel = "menus_seleccionados.xlsx"
    if not os.path.isfile(archivo_excel):
        return render_template('admin.html', error="No hay pedidos registrados aún.", resumen_datos=None, graficos=None, logistica=None)

    pedidos = pd.read_excel(archivo_excel, engine="openpyxl")

    # Asegurarse de que 'Fecha de Pedido' esté en formato datetime
    if 'Fecha de Pedido' in pedidos.columns:
        pedidos['Fecha de Pedido'] = pd.to_datetime(pedidos['Fecha de Pedido'], errors='coerce')

    # Verificar si hay valores inválidos en la columna después de la conversión
    if pedidos['Fecha de Pedido'].isnull().any():
        return "Hay valores no válidos en la columna 'Fecha de Pedido'. Verifica los datos en el archivo.", 500

    global menu_semanal

    # Leer los platos del archivo Excel
    try:
        platos_df = pd.read_excel("platos.xlsx", engine="openpyxl")
        platos_df.columns = platos_df.columns.str.strip()
        platos = platos_df['Plato'].dropna().tolist()
    except Exception as e:
        return f"Error al procesar el archivo Excel: {e}", 500

    if request.method == 'POST':
        # Procesar datos enviados
        menu_semanal = {
            dia: request.form.getlist(f'menu_{dia}[]') for dia in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
        }
        print("Menú actualizado:", menu_semanal)

    # Aplicar filtros desde el formulario
    filtro_dia = request.form.get('filtro_dia', None)
    fecha_inicio = request.form.get('fecha_inicio', None)
    fecha_fin = request.form.get('fecha_fin', None)
    cliente_nombre = request.form.get('cliente_nombre', None)
    # Filtro por rango de fechas
    if fecha_inicio:
        pedidos = pedidos[pedidos['Fecha de Pedido'] >= pd.to_datetime(fecha_inicio)]
    if fecha_fin:
        pedidos = pedidos[pedidos['Fecha de Pedido'] <= pd.to_datetime(fecha_fin)]
    # Filtro por cliente
    if cliente_nombre:
        pedidos = pedidos[pedidos['Nombre Completo'].str.contains(cliente_nombre, case=False, na=False)]
    
    # Resumen Logística por Día
    logistica_data = None

    # Asegurarse de que los datos de "Día de la Semana" son consistentes
    if 'Día de la Semana' in pedidos.columns:
            pedidos['Día de la Semana'] = pedidos['Día de la Semana'].astype(str).str.strip()

    if filtro_dia:
    # Filtrar por día específico
        logistica_data = pedidos[pedidos['Día de la Semana'] == filtro_dia].groupby(
        ['Nombre Completo', 'Telefono', 'Dirección de envio', 'Empresa']
        ).apply(lambda x: ", ".join([f"{row['Cantidad']}x {row['Plato']}" for _, row in x.iterrows()]))
    else:
    # Sin filtro, considerar todos los días
        logistica_data = pedidos.groupby(
        ['Nombre Completo', 'Telefono', 'Dirección de envio', 'Empresa']
    ).apply(lambda x: ", ".join([f"{row['Cantidad']}x {row['Plato']}" for _, row in x.iterrows()]))

    # Convertir a DataFrame asegurando no conflictos de índice
    logistica_data = logistica_data.reset_index(drop=False)

    #Eliminar columnas duplicadas en caso de conflicto
    if 'Empresa' in logistica_data.columns and 'Empresa' in logistica_data.index.names:
        logistica_data = logistica_data.loc[:, ~logistica_data.columns.duplicated()]

    # Renombrar las columnas para mantener consistencia
    logistica_data.columns = ['Nombre Completo', 'Telefono', 'Dirección de envio', 'Empresa', 'Platos y Cantidades']


    
    # Generar Resumen Semanal y Guardarlo en una Hoja Nueva
    if not pedidos.empty:
    # Asegurarte de que los días están en el orden correcto
        pedidos['Día de la Semana'] = pd.Categorical(
        pedidos['Día de la Semana'],
        categories=["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"],
        ordered=True
    )

    resumen_semanal = pedidos.pivot_table(
        index='Plato',
        columns='Día de la Semana',
        values='Cantidad',
        aggfunc='sum',
        fill_value=0
    )

    # Añadir una columna con el total por plato
    resumen_semanal['Total'] = resumen_semanal.sum(axis=1)
    # Añadir una fila con el total general por día
    resumen_semanal.loc['Total'] = resumen_semanal.sum(axis=0)

    # Resetear el índice para una presentación tabular limpia
    resumen_semanal = resumen_semanal.reset_index()

    # Guardar en una nueva hoja llamada "Resumen Semanal"
    with pd.ExcelWriter(archivo_excel, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
        resumen_semanal.to_excel(writer, sheet_name='Resumen Semanal', index=False)

    # Generar gráficos dinámicos
    graficos = {}
    if not pedidos.empty:
        # Consumo por Cliente
        grafico_cliente = pedidos.groupby('Nombre Completo')['Cantidad'].sum()
        fig, ax = plt.subplots()
        grafico_cliente.plot(kind='bar', ax=ax, color='teal')
        ax.set_title("Consumo por Cliente")
        ax.set_xlabel("Cliente")
        ax.set_ylabel("Cantidad")
        fig.tight_layout()
        img = io.BytesIO()
        plt.savefig(img, format='png')
        img.seek(0)
        graficos['consumo_por_cliente'] = f"data:image/png;base64,{base64.b64encode(img.getvalue()).decode()}"

        # Distribución por Plato
        data = pedidos.groupby('Plato')['Cantidad'].sum()
        data = data.sort_values(ascending=False)
        threshold = 0.03
        total = data.sum()
        data = pd.concat([
            data[data / total > threshold],
            pd.Series(data[data / total <= threshold].sum(), index=["Otros"])
        ])
        fig, ax = plt.subplots(figsize=(8, 8))
        wedges, texts, autotexts = ax.pie(
            data,
            labels=data.index,
            autopct='%1.1f%%',
            startangle=90,
            wedgeprops=dict(edgecolor='w'),
            explode=[0.1 if i == 0 else 0 for i in range(len(data))],
            pctdistance=0.85,
            labeldistance=1.1
        )
        for text in texts:
            text.set_fontsize(10)
        for autotext in autotexts:
            autotext.set_color('black')
            autotext.set_fontsize(9)
        ax.set_title("Distribución por Plato", fontsize=14, weight='bold')
        centre_circle = plt.Circle((0, 0), 0.70, fc='white')
        fig.gca().add_artist(centre_circle)
        fig.tight_layout()
        img = io.BytesIO()
        plt.savefig(img, format='png', bbox_inches='tight')
        img.seek(0)
        graficos['consumo_por_plato'] = f"data:image/png;base64,{base64.b64encode(img.getvalue()).decode()}"


        # Evolución de Pedidos por Día de la Semana
        pedidos['Día de la Semana'] = pd.Categorical(pedidos['Día de la Semana'], categories=["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"], ordered=True)
        pedidos['Semana'] = pedidos['Fecha de Pedido'].dt.isocalendar().week
        semanas = pedidos['Semana'].unique()
        if len(semanas) >= 2:
            semana_actual = semanas[-1]
            semana_anterior = semanas[-2]
            evolucion_actual = pedidos[pedidos['Semana'] == semana_actual].groupby('Día de la Semana')['Cantidad'].sum()
            evolucion_anterior = pedidos[pedidos['Semana'] == semana_anterior].groupby('Día de la Semana')['Cantidad'].sum()
            fig, ax = plt.subplots()
            evolucion_actual.reindex(["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]).plot(ax=ax, label="Semana Actual", marker='o', linestyle='-')
            evolucion_anterior.reindex(["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]).plot(ax=ax, label="Semana Anterior", marker='o', linestyle='--')
            ax.set_title("Evolución de Pedidos por Día de la Semana")
            ax.set_xlabel("Día de la Semana")
            ax.set_ylabel("Cantidad")
            ax.legend()
            fig.tight_layout()
            img = io.BytesIO()
            plt.savefig(img, format='png')
            img.seek(0)
            graficos['evolucion_pedidos'] = f"data:image/png;base64,{base64.b64encode(img.getvalue()).decode()}"

    return render_template(
        'admin.html',
        resumen_datos=logistica_data,
        graficos=graficos,
        logistica=logistica_data,
        filtro_dia=filtro_dia,
        platos=platos,
        menu=menu_semanal
    )

# Ruta para descargar el archivo logistica
@app.route('/download_logistica_pdf/<filtro_dia>')
def download_logistica_pdf(filtro_dia):
    archivo_excel = "menus_seleccionados.xlsx"
    if not os.path.isfile(archivo_excel):
        return redirect(url_for('admin'))

    pedidos = pd.read_excel(archivo_excel, engine="openpyxl")
    logistica_data = pedidos[pedidos['Día de la Semana'] == filtro_dia].groupby(
        ['Nombre Completo', 'Telefono', 'Dirección de envio']
    ).apply(lambda x: ", ".join([f"{row['Cantidad']}x {row['Plato']}" for _, row in x.iterrows()])) \
     .reset_index(name="Platos y Cantidades")

    # Generar PDF
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer)
    p.setTitle(f"Logística - {filtro_dia}")

    p.drawString(100, 800, f"Hoja Logística - {filtro_dia}")
    y = 780

    # Crear la tabla en PDF
    for index, row in logistica_data.iterrows():
        p.drawString(100, y, f"Nombre: {row['Nombre Completo']}")
        p.drawString(100, y - 20, f"Teléfono: {row['Telefono']}")
        p.drawString(100, y - 40, f"Dirección: {row['Dirección de envio']}")
        p.drawString(100, y - 60, f"Platos y Cantidades: {row['Platos y Cantidades']}")
        y -= 100

        if y < 50:  # Salto de página si no hay espacio
            p.showPage()
            y = 780

    p.save()
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name=f"logistica_{filtro_dia}.pdf")

# Ruta de registro
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Crear nuevo cliente
        nuevo_cliente = {
            "Correo electronico": request.form.get("Correo Electronico").strip().lower(),
            "Nombre Completo": request.form.get("Nombre Completo").strip(),
            "Telefono": request.form.get("Telefono").strip(),
            "Dirección de envio": request.form.get("Dirección de Envio").strip(),
            "Empresa": request.form.get("Empresa").strip()
        }

        # Cargar la base de datos actual
        clientes = cargar_clientes()

        # Verificar si el correo ya existe
        if nuevo_cliente["Correo electronico"] in clientes["Correo electronico"].values:
            return render_template('register.html', error="El correo ya está registrado.")

        # Guardar el nuevo cliente en la base de datos
        clientes = pd.concat([clientes, pd.DataFrame([nuevo_cliente])], ignore_index=True)
        clientes.to_excel(r"C:\Users\Joaqu\OneDrive\Desktop\web_fabrica\templates\Clientes.xlsx", index=False, engine="openpyxl")

        return redirect(url_for('login'))

    return render_template('register.html')

# Ruta para el menú
@app.route('/menu', methods=['GET', 'POST'])
def menu_route():
    if 'user' not in session:
        return redirect(url_for('login'))

    global menu_semanal

    # Obtener los datos del cliente desde la sesión
    datos_cliente = session.get('datos_cliente', {})
    if not datos_cliente:
        return "Datos del cliente no encontrados. Por favor, inicie sesión nuevamente.", 400

    if request.method == 'POST':
        # Procesar selección de platos
        seleccion = {}
        for dia, platos_dia in menu_semanal.items():
            # Obtener los platos y las cantidades enviadas en el formulario
            platos_dia = request.form.getlist(f'{dia}_plato')
            cantidades_dia = request.form.getlist(f'{dia}_cantidad')

            print(f"Procesando selección para {dia}: {platos_dia} con cantidades {cantidades_dia}")
            
            # Guardar platos seleccionados con cantidades mayores a 0
            seleccion[dia] = [
                {"plato": plato, "cantidad": int(cantidad)}
                for plato, cantidad in zip(platos_dia, cantidades_dia)
                if cantidad.isdigit() and int(cantidad) > 0
            ]

        print("Selección final procesada:", seleccion)
        
        # Guardar el pedido en la sesión
        session['pedido'] = {
            "datos_cliente": datos_cliente,
            "seleccion": seleccion,
            "observaciones": request.form.get('observaciones', "").strip()
        }

        print("Pedido registrado en sesión:", session['pedido'])
        return redirect(url_for('resumen'))

    # Renderizar el formulario con el menú semanal
    return render_template('index.html', menu=menu_semanal, datos_cliente=datos_cliente)


# Ruta para el proceso de resumen
@app.route('/resumen', methods=['GET', 'POST'])
def resumen():
    # Verificar si hay un pedido en la sesión
    if 'pedido' not in session:
        return redirect(url_for('menu_route'))

    pedido = session['pedido']
    print("Contenido de session['pedido'] en /resumen:", pedido)
    hoy = datetime.now()
    dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
    fechas_entrega = {
        dia: (hoy + timedelta(days=(i - hoy.weekday()) % 7)).strftime("%Y/%m/%d")
        for i, dia in enumerate(dias_semana)
    }
    # Generar filas para el resumen
    filas_pedido = []
    for dia, platos in pedido['seleccion'].items():
        for plato_info in platos:
            filas_pedido.append({
                "Fecha de Pedido": hoy.strftime("%Y/%m/%d"),
                "Nombre Completo": pedido["datos_cliente"].get("Nombre Completo", "N/A"),
                "Correo electronico": session.get('user', "N/A"),
                "Telefono": pedido["datos_cliente"].get("Telefono", "N/A"),
                "Dirección de envio": pedido["datos_cliente"].get("Dirección de envio", "N/A"),
                "Empresa": pedido["datos_cliente"].get("Empresa", "N/A"),
                "Día de la Semana": dia,
                "Plato": plato_info.get("plato", "N/A"),
                "Cantidad": plato_info.get("cantidad", 0),
                "Fecha de Entrega": fechas_entrega[dia],
                "Observaciones": pedido.get("observaciones", "")
            })

    # Si el usuario confirma el pedido (método POST)
    if request.method == 'POST':
        archivo_excel = "menus_seleccionados.xlsx"

        # Guardar los datos del pedido en un archivo Excel
        df_nuevo = pd.DataFrame(filas_pedido)
        if not os.path.isfile(archivo_excel):
            df_nuevo.to_excel(archivo_excel, index=False, engine="openpyxl")
        else:
            df_existente = pd.read_excel(archivo_excel, engine="openpyxl")
            df_final = pd.concat([df_existente, df_nuevo], ignore_index=True)
            df_final.to_excel(archivo_excel, index=False, engine="openpyxl")

        # Enviar correos al cliente y al administrador
        mensaje_cliente = f"""
        Hola {pedido["datos_cliente"].get("Nombre Completo", "Cliente")},

        Gracias por realizar tu pedido. Estos son los detalles:
        """
        for dia, platos in pedido['seleccion'].items():
            mensaje_cliente += f"\n{dia}:\n"
            for plato_info in platos:
                mensaje_cliente += f"- {plato_info['plato']} (Cantidad: {plato_info['cantidad']})\n"
        mensaje_cliente += f"\nObservaciones: {pedido.get('observaciones', 'Sin observaciones')}"

        enviar_correo(
            destinatario=pedido["datos_cliente"].get("Correo electronico", "correo@default.com"),
            asunto="Confirmación de tu pedido",
            mensaje=mensaje_cliente
        )

        mensaje_admin = f"""
        Nuevo pedido recibido:

        Cliente: {pedido["datos_cliente"].get("Nombre Completo", "N/A")}
        Empresa: {pedido["datos_cliente"].get("Empresa", "N/A")}
        Dirección de envío: {pedido["datos_cliente"].get("Dirección de envio", "N/A")}
        Teléfono: {pedido["datos_cliente"].get("Telefono", "N/A")}
        Correo: {pedido["datos_cliente"].get("Correo electronico", "N/A")}

        Detalles del pedido:
        """
        for dia, platos in pedido['seleccion'].items():
            mensaje_admin += f"\n{dia}:\n"
            for plato_info in platos:
                mensaje_admin += f"- {plato_info['plato']} (Cantidad: {plato_info['cantidad']})\n"
        mensaje_admin += f"\nObservaciones: {pedido.get('observaciones', 'Sin observaciones')}"

        enviar_correo(
            destinatario="joaquingonzalez@higoma.es",
            asunto="Nuevo pedido recibido",
            mensaje=mensaje_admin
        )

        # Limpiar el pedido de la sesión y mostrar página de éxito
        session.pop('pedido', None)
        return render_template('success.html',nombre=pedido["datos_cliente"].get("Nombre Completo", "Cliente"),pedido=pedido,
        direccion_envio=pedido["datos_cliente"].get("Dirección de envio", ""),)

    # Renderizar la plantilla de resumen con las filas generadas
    return render_template('resumen.html', resumen_organizado=filas_pedido)


   
# Ruta para descargar el archivo con el Resumen Semanal
@app.route('/download_resumen')
def download_resumen():
    archivo_excel = "menus_seleccionados.xlsx"
    if os.path.exists(archivo_excel):
        return send_file(archivo_excel, as_attachment=True, download_name="resumen_semanal.xlsx")
    return redirect(url_for('admin'))



# Ruta para cerrar sesión
@app.route('/logout')
def logout():
    session.clear()  # Limpia la sesión del usuario
    return redirect(url_for('login'))  # Redirige al login

# Esto debe aparecer **solo una vez** al final del archivo
if __name__ == '__main__':
    app.run(debug=True)

