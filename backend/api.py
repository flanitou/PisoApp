"""Phase 2 API on Silence's Flask application and native session tokens."""

from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import wraps

import pymysql
from flask import jsonify, request
from silence.auth.tokens import check_token
from silence.db.connector import get_conn
from silence.exceptions import HTTPError, TokenError


@contextmanager
def database():
    connection = get_conn()
    try:
        yield connection.cursor(pymysql.cursors.DictCursor)
        connection.commit()
    except pymysql.IntegrityError as exc:
        connection.rollback()
        if exc.args[0] == 1062:
            raise HTTPError(409, "Ya existe un registro con esos datos") from exc
        if exc.args[0] == 1452:
            raise HTTPError(400, "No existe el registro relacionado") from exc
        raise
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def one(cursor, sql, params=()):
    cursor.execute(sql, params)
    return cursor.fetchone()


def many(cursor, sql, params=()):
    cursor.execute(sql, params)
    return cursor.fetchall()


def authenticated(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        token = request.headers.get("Token")
        if not token:
            raise HTTPError(401, "Falta el token de sesión (cabecera Token)")
        try:
            claims = check_token(token)
            user_id = claims["user_id"]
        except (TokenError, KeyError, TypeError):
            raise HTTPError(401, "Token de sesión inválido")
        # Silence embeds the role in the token. Always consult the live role:
        # manual promotions and revocations must take effect immediately.
        with database() as cursor:
            user = one(cursor, "SELECT user_id, role FROM users WHERE user_id = %s", (user_id,))
        if not user:
            raise HTTPError(401, "El usuario ya no existe")
        return view(user, *args, **kwargs)

    return wrapper


def body(allowed):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise HTTPError(400, "Se requiere un objeto JSON")
    if set(data) - set(allowed):
        raise HTTPError(400, "El cuerpo contiene campos no permitidos")
    return data


def text(data, key, limit=None, optional=False, default=None):
    value = data.get(key, default)
    if value is None and optional:
        return None
    if not isinstance(value, str) or (not optional and not value.strip()):
        raise HTTPError(400, f"El campo {key} debe ser texto no vacío")
    if limit and len(value) > limit:
        raise HTTPError(400, f"El campo {key} supera {limit} caracteres")
    return value.strip()


def day(data, key):
    try:
        return date.fromisoformat(text(data, key))
    except ValueError as exc:
        raise HTTPError(400, f"{key} debe tener formato AAAA-MM-DD") from exc


def timestamp(data, key):
    try:
        value = datetime.fromisoformat(text(data, key))
        if value.tzinfo is not None:
            raise ValueError("Se espera hora local sin zona horaria")
        return value
    except ValueError as exc:
        raise HTTPError(400, f"{key} debe ser una fecha y hora ISO local") from exc


def positive_id(data, key):
    value = data.get(key)
    if type(value) is not int or value < 1:
        raise HTTPError(400, f"{key} debe ser un entero positivo")
    return value


def price(data):
    try:
        value = Decimal(str(data.get("coste_total", "0.00")))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise HTTPError(400, "coste_total no es válido") from exc
    if not value.is_finite() or value < 0 or value > Decimal("999999.99") or value.as_tuple().exponent < -2:
        raise HTTPError(400, "coste_total debe ser positivo y tener como máximo dos decimales")
    return value


def require_owner(cursor, table, pk, record_id, user_id):
    if not one(cursor, f"SELECT 1 FROM {table} WHERE {pk} = %s AND creado_por = %s", (record_id, user_id)):
        raise HTTPError(404, "Registro no encontrado o sin permiso")


def register_routes(app):
    @app.get("/api/actividades")
    @authenticated
    def activities(user):
        with database() as cursor:
            rows = many(cursor, "SELECT actividad_id, titulo, descripcion, DATE_FORMAT(fecha_hora, '%%Y-%%m-%%dT%%H:%%i:%%s') AS fecha_hora, lugar, creado_por, generada_por_comida FROM actividades ORDER BY fecha_hora")
        return jsonify(rows)

    @app.get("/api/actividades/<int:activity_id>")
    @authenticated
    def activity(user, activity_id):
        with database() as cursor:
            row = one(cursor, "SELECT actividad_id, titulo, descripcion, DATE_FORMAT(fecha_hora, '%%Y-%%m-%%dT%%H:%%i:%%s') AS fecha_hora, lugar, creado_por, generada_por_comida FROM actividades WHERE actividad_id = %s", (activity_id,))
        if not row:
            raise HTTPError(404, "Actividad no encontrada")
        return jsonify(row)

    @app.post("/api/actividades")
    @authenticated
    def create_activity(user):
        data = body(("titulo", "descripcion", "fecha_hora", "lugar"))
        values = (text(data, "titulo", 100), text(data, "descripcion", optional=True), timestamp(data, "fecha_hora"), text(data, "lugar", 100, default="En el piso"), user["user_id"])
        with database() as cursor:
            cursor.execute("INSERT INTO actividades (titulo, descripcion, fecha_hora, lugar, creado_por) VALUES (%s, %s, %s, %s, %s)", values)
            new_id = cursor.lastrowid
        return jsonify({"actividad_id": new_id}), 201

    @app.put("/api/actividades/<int:activity_id>")
    @authenticated
    def edit_activity(user, activity_id):
        data = body(("titulo", "descripcion", "fecha_hora", "lugar"))
        values = (text(data, "titulo", 100), text(data, "descripcion", optional=True), timestamp(data, "fecha_hora"), text(data, "lugar", 100, default="En el piso"), activity_id)
        with database() as cursor:
            require_owner(cursor, "actividades", "actividad_id", activity_id, user["user_id"])
            cursor.execute("UPDATE actividades SET titulo=%s, descripcion=%s, fecha_hora=%s, lugar=%s WHERE actividad_id=%s", values)
        return jsonify({"actividad_id": activity_id})

    @app.delete("/api/actividades/<int:activity_id>")
    @authenticated
    def delete_activity(user, activity_id):
        with database() as cursor:
            require_owner(cursor, "actividades", "actividad_id", activity_id, user["user_id"])
            cursor.execute("DELETE FROM actividades WHERE actividad_id=%s", (activity_id,))
        return "", 204

    @app.get("/api/comidas")
    @authenticated
    def meals(user):
        with database() as cursor:
            rows = many(cursor, "SELECT c.comida_id, c.actividad_id, c.nombre_evento, c.menu_platos, c.coste_total, DATE_FORMAT(c.fecha, '%%Y-%%m-%%dT%%H:%%i:%%s') AS fecha, a.creado_por FROM comidas_especiales c JOIN actividades a ON a.actividad_id=c.actividad_id ORDER BY c.fecha")
        return jsonify(rows)

    @app.get("/api/comidas/<int:meal_id>")
    @authenticated
    def meal(user, meal_id):
        with database() as cursor:
            row = one(cursor, "SELECT c.comida_id, c.actividad_id, c.nombre_evento, c.menu_platos, c.coste_total, DATE_FORMAT(c.fecha, '%%Y-%%m-%%dT%%H:%%i:%%s') AS fecha, a.creado_por FROM comidas_especiales c JOIN actividades a ON a.actividad_id=c.actividad_id WHERE c.comida_id=%s", (meal_id,))
        if not row:
            raise HTTPError(404, "Comida no encontrada")
        return jsonify(row)

    @app.post("/api/comidas")
    @authenticated
    def create_meal(user):
        data = body(("actividad_id", "nombre_evento", "menu_platos", "coste_total", "fecha"))
        activity_id = positive_id(data, "actividad_id") if data.get("actividad_id") is not None else None
        name = text(data, "nombre_evento", 100)
        menu = text(data, "menu_platos")
        cost = price(data)
        when = timestamp(data, "fecha")
        with database() as cursor:
            if activity_id is None:
                cursor.execute("INSERT INTO actividades (titulo, fecha_hora, creado_por, generada_por_comida) VALUES (%s, %s, %s, 1)", (name, when, user["user_id"]))
                activity_id = cursor.lastrowid
            else:
                require_owner(cursor, "actividades", "actividad_id", activity_id, user["user_id"])
            cursor.execute("INSERT INTO comidas_especiales (actividad_id, nombre_evento, menu_platos, coste_total, fecha) VALUES (%s, %s, %s, %s, %s)", (activity_id, name, menu, cost, when))
            new_id = cursor.lastrowid
        return jsonify({"comida_id": new_id, "actividad_id": activity_id}), 201

    @app.put("/api/comidas/<int:meal_id>")
    @authenticated
    def edit_meal(user, meal_id):
        data = body(("nombre_evento", "menu_platos", "coste_total", "fecha"))
        values = (text(data, "nombre_evento", 100), text(data, "menu_platos"), price(data), timestamp(data, "fecha"), meal_id)
        with database() as cursor:
            meal = one(cursor, "SELECT c.actividad_id, a.generada_por_comida FROM comidas_especiales c JOIN actividades a ON a.actividad_id=c.actividad_id WHERE c.comida_id=%s AND a.creado_por=%s", (meal_id, user["user_id"]))
            if not meal:
                raise HTTPError(404, "Comida no encontrada o sin permiso")
            cursor.execute("UPDATE comidas_especiales SET nombre_evento=%s, menu_platos=%s, coste_total=%s, fecha=%s WHERE comida_id=%s", values)
            if meal["generada_por_comida"] and not one(cursor, "SELECT 1 FROM comidas_especiales WHERE actividad_id=%s AND comida_id<>%s LIMIT 1", (meal["actividad_id"], meal_id)):
                cursor.execute("UPDATE actividades SET titulo=%s, fecha_hora=%s WHERE actividad_id=%s", (values[0], values[3], meal["actividad_id"]))
        return jsonify({"comida_id": meal_id})

    @app.delete("/api/comidas/<int:meal_id>")
    @authenticated
    def delete_meal(user, meal_id):
        with database() as cursor:
            meal = one(cursor, "SELECT c.actividad_id, a.generada_por_comida FROM comidas_especiales c JOIN actividades a ON a.actividad_id=c.actividad_id WHERE c.comida_id=%s AND a.creado_por=%s", (meal_id, user["user_id"]))
            if not meal:
                raise HTTPError(404, "Comida no encontrada o sin permiso")
            cursor.execute("DELETE FROM comidas_especiales WHERE comida_id=%s", (meal_id,))
            if meal["generada_por_comida"] and not one(cursor, "SELECT 1 FROM comidas_especiales WHERE actividad_id=%s LIMIT 1", (meal["actividad_id"],)):
                cursor.execute("DELETE FROM actividades WHERE actividad_id=%s", (meal["actividad_id"],))
        return "", 204

    @app.get("/api/actividades/<int:activity_id>/asistencias")
    @authenticated
    def attendance(user, activity_id):
        with database() as cursor:
            if not one(cursor, "SELECT 1 FROM actividades WHERE actividad_id=%s", (activity_id,)):
                raise HTTPError(404, "Actividad no encontrada")
            rows = many(cursor, "SELECT s.asistencia_id, s.usuario_id, u.username, s.estado FROM asistencias s JOIN users u ON u.user_id=s.usuario_id WHERE s.actividad_id=%s ORDER BY u.username", (activity_id,))
        return jsonify(rows)

    @app.post("/api/actividades/<int:activity_id>/asistencia")
    @authenticated
    def attend(user, activity_id):
        data = body(("estado",))
        state = text(data, "estado", default="confirmado")
        if state not in ("confirmado", "pendiente", "rechazado"):
            raise HTTPError(400, "Estado de asistencia no válido")
        with database() as cursor:
            if not one(cursor, "SELECT 1 FROM actividades WHERE actividad_id=%s", (activity_id,)):
                raise HTTPError(404, "Actividad no encontrada")
            cursor.execute("INSERT INTO asistencias (actividad_id, usuario_id, estado) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE estado=VALUES(estado)", (activity_id, user["user_id"], state))
        return jsonify({"actividad_id": activity_id, "estado": state})

    @app.delete("/api/actividades/<int:activity_id>/asistencia")
    @authenticated
    def cancel_attendance(user, activity_id):
        with database() as cursor:
            cursor.execute("DELETE FROM asistencias WHERE actividad_id=%s AND usuario_id=%s", (activity_id, user["user_id"]))
            if not cursor.rowcount:
                raise HTTPError(404, "Asistencia no encontrada")
        return "", 204

    @app.get("/api/pernoctaciones")
    @authenticated
    def nights(user):
        query = "SELECT p.pernoctacion_id, p.usuario_id, u.username, DATE_FORMAT(p.fecha, '%%Y-%%m-%%d') AS fecha, p.notas, p.estado, p.validado_por, DATE_FORMAT(p.fecha_validacion, '%%Y-%%m-%%dT%%H:%%i:%%s') AS fecha_validacion FROM pernoctaciones p JOIN users u ON u.user_id=p.usuario_id"
        if user["role"] == "resident":
            query += " ORDER BY p.fecha DESC"
            params = ()
        else:
            query += " WHERE p.usuario_id=%s ORDER BY p.fecha DESC"
            params = (user["user_id"],)
        with database() as cursor:
            rows = many(cursor, query, params)
        return jsonify(rows)

    @app.post("/api/pernoctaciones")
    @authenticated
    def create_night(user):
        if user["role"] != "guest":
            raise HTTPError(403, "Solo los invitados pueden anotar pernoctaciones")
        data = body(("fecha", "notas"))
        values = (user["user_id"], day(data, "fecha"), text(data, "notas", 255, optional=True))
        with database() as cursor:
            cursor.execute("INSERT INTO pernoctaciones (usuario_id, fecha, notas) VALUES (%s, %s, %s)", values)
            new_id = cursor.lastrowid
        return jsonify({"pernoctacion_id": new_id, "estado": "pendiente"}), 201

    @app.put("/api/pernoctaciones/<int:night_id>")
    @authenticated
    def edit_night(user, night_id):
        if user["role"] != "guest":
            raise HTTPError(403, "Solo los invitados pueden editar sus pernoctaciones")
        data = body(("fecha", "notas"))
        values = (day(data, "fecha"), text(data, "notas", 255, optional=True), night_id, user["user_id"])
        with database() as cursor:
            cursor.execute("UPDATE pernoctaciones SET fecha=%s, notas=%s, estado='pendiente', validado_por=NULL, fecha_validacion=NULL WHERE pernoctacion_id=%s AND usuario_id=%s AND estado IN ('pendiente','rechazada')", values)
            if not cursor.rowcount:
                raise HTTPError(404, "Pernoctación inexistente o ya aprobada")
        return jsonify({"pernoctacion_id": night_id, "estado": "pendiente"})

    @app.delete("/api/pernoctaciones/<int:night_id>")
    @authenticated
    def delete_night(user, night_id):
        if user["role"] != "guest":
            raise HTTPError(403, "Solo los invitados pueden borrar sus pernoctaciones")
        with database() as cursor:
            cursor.execute("DELETE FROM pernoctaciones WHERE pernoctacion_id=%s AND usuario_id=%s AND estado IN ('pendiente','rechazada')", (night_id, user["user_id"]))
            if not cursor.rowcount:
                raise HTTPError(404, "Pernoctación inexistente o ya aprobada")
        return "", 204

    @app.put("/api/pernoctaciones/<int:night_id>/validacion")
    @authenticated
    def validate_night(user, night_id):
        if user["role"] != "resident":
            raise HTTPError(403, "Solo los anfitriones pueden validar pernoctaciones")
        data = body(("estado",))
        state = text(data, "estado")
        if state not in ("aprobada", "rechazada"):
            raise HTTPError(400, "estado debe ser aprobada o rechazada")
        with database() as cursor:
            row = one(cursor, "SELECT p.usuario_id, p.estado, u.role FROM pernoctaciones p JOIN users u ON u.user_id=p.usuario_id WHERE p.pernoctacion_id=%s FOR UPDATE", (night_id,))
            if not row or row["estado"] != "pendiente" or row["role"] != "guest" or row["usuario_id"] == user["user_id"]:
                raise HTTPError(409, "No hay una pernoctación pendiente de un invitado")
            cursor.execute("UPDATE pernoctaciones SET estado=%s, validado_por=%s, fecha_validacion=NOW() WHERE pernoctacion_id=%s", (state, user["user_id"], night_id))
        return jsonify({"pernoctacion_id": night_id, "estado": state})

    @app.get("/api/ranking/pernoctaciones")
    @authenticated
    def night_ranking(user):
        with database() as cursor:
            rows = many(cursor, "SELECT RANK() OVER (ORDER BY noches DESC) AS posicion, usuario_id, username, noches FROM (SELECT u.user_id AS usuario_id, u.username, COUNT(p.pernoctacion_id) AS noches FROM users u JOIN pernoctaciones p ON p.usuario_id=u.user_id AND p.estado='aprobada' WHERE u.role='guest' GROUP BY u.user_id, u.username) AS conteo ORDER BY posicion, username")
        return jsonify(rows)
