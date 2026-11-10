# Piso Gay — web y API local

## Arranque

Si aún no tienes `.env`, copia `.env.example` a `.env` y cambia sus secretos. Después:

```bash
docker compose up --build -d
docker compose ps
```

Abre **http://localhost:8080** para usar la web en el navegador. Nginx sirve la SPA y envía las peticiones `/api/` al backend sin cambiar su ruta. Para pruebas directas, la API también está en `http://localhost:8000/api`.

La base existente se conserva: al arrancar, el backend crea las tablas nuevas si faltan y cambia el valor por defecto del rol a `guest`, sin modificar los usuarios `resident` anteriores. **No uses `docker compose down -v`** si quieres conservar los datos.

La web guarda el token de sesión en `localStorage` para recordar el acceso. Antes de exponerla fuera de tu equipo necesitarás HTTPS, revisar la política de seguridad de los tokens y actualizar las dependencias heredadas de Silence; Compose solo publica la web en `localhost` por defecto.

## Fotos de perfil

Pulsa tu nombre en la cabecera para abrir **Mi perfil**. Puedes subir una foto JPG, PNG o WebP de hasta 2 MB, o eliminarla. La imagen se recorta a 256 × 256 píxeles y se vuelve a codificar como WebP para descartar metadatos. Aparece junto a tu nombre, en el ranking y en las asistencias; quien no tenga foto verá un corazón. Solo tú puedes modificar tu foto.

Las fotos no son archivos públicos: la ruta `GET /api/users/{id}/avatar` exige el token de sesión de Silence. Las subidas se guardan en el volumen Docker `avatar_data`, independiente del de MariaDB. Para subir desde otro cliente, envía `POST /api/users/me/avatar` como `multipart/form-data` con el campo `avatar` y la cabecera `Token`. `DELETE /api/users/me/avatar` elimina la foto. Puedes consultar tu rol y el estado del avatar con `GET /api/users/me`.

## Roles y autenticación

`POST /api/register` crea usuarios `guest` aunque el cliente envíe otro rol. Los `resident` existentes son anfitriones. Para convertir manualmente un invitado en anfitrión (solo un operador con acceso a MariaDB):

```sql
UPDATE users SET role = 'resident' WHERE username = 'nombre_del_usuario';
```

Tras la promoción, vuelve a iniciar sesión. Las rutas de esta fase comprueban el rol actual en MariaDB. El token de Silence va en la cabecera **`Token`** (no en `Authorization: Bearer`); es un token de sesión firmado, no JWT.

```bash
curl -X POST http://localhost:8000/api/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"invitado1","email":"invitado1@example.com","password":"ClaveSegura123!"}'

curl -X POST http://localhost:8000/api/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"invitado1","password":"ClaveSegura123!"}'
```

Guarda el campo `sessionToken` devuelto por login y úsalo en las demás peticiones:

```bash
curl -X POST http://localhost:8000/api/pernoctaciones \
  -H 'Content-Type: application/json' \
  -H 'Token: TU_SESSION_TOKEN' \
  -d '{"fecha":"2026-11-09","notas":"Me quedé en el piso"}'

curl -H 'Token: TU_SESSION_TOKEN' http://localhost:8000/api/ranking/pernoctaciones
```

Solo los invitados pueden anotar sus propias noches (una por día). Un anfitrión valida una anotación pendiente así:

```bash
curl -X PUT http://localhost:8000/api/pernoctaciones/1/validacion \
  -H 'Content-Type: application/json' \
  -H 'Token: TOKEN_DE_UN_ANFITRION' \
  -d '{"estado":"aprobada"}'
```

Para rechazarla, usa `"estado":"rechazada"`. Solo las noches aprobadas suman en el ranking, con empates. Un invitado puede editar y volver a enviar una noche rechazada, o borrar una pendiente/rechazada; no puede alterar una aprobada.

## Rutas de la fase 2

Todas requieren la cabecera `Token`:

| Método | Ruta | Uso |
| --- | --- | --- |
| GET, POST | `/api/actividades` | Listar o crear actividades |
| GET, PUT, DELETE | `/api/actividades/{id}` | Consultar o gestionar una actividad (modifica solo su creador) |
| GET, POST | `/api/comidas` | Listar o crear comidas. Al crear, indicar `nombre_evento`, `menu_platos`, `fecha` y, opcionalmente, `coste_total`. Si no se indica `actividad_id`, se crea un plan asociado automáticamente |
| GET, PUT, DELETE | `/api/comidas/{id}` | Consultar, modificar o borrar una comida (modifica solo el creador de su actividad) |
| GET | `/api/actividades/{id}/asistencias` | Ver asistencias, también a comidas vinculadas |
| POST, DELETE | `/api/actividades/{id}/asistencia` | Registrar/actualizar o cancelar la asistencia propia |
| GET, POST | `/api/pernoctaciones` | Ver noches (anfitrión: todas; invitado: propias) o solicitar una propia |
| PUT, DELETE | `/api/pernoctaciones/{id}` | Editar o borrar una noche propia pendiente/rechazada |
| PUT | `/api/pernoctaciones/{id}/validacion` | Aprobar/rechazar noche pendiente (solo anfitrión) |
| GET | `/api/ranking/pernoctaciones` | Ranking de invitados por noches aprobadas |

Los campos de fecha usan `AAAA-MM-DD` y los de fecha y hora `AAAA-MM-DDTHH:MM:SS` (hora local, sin zona). Ejemplo de creación de actividad:

```bash
curl -X POST http://localhost:8000/api/actividades \
  -H 'Content-Type: application/json' \
  -H 'Token: TU_SESSION_TOKEN' \
  -d '{"titulo":"Cena de viernes","descripcion":"Cenamos juntos","fecha_hora":"2026-12-04T21:00:00","lugar":"En el piso"}'
```

Las actividades y comidas no requieren aprobación. Al eliminar una actividad se eliminan sus comidas y asistencias vinculadas.
Si eliminas una comida cuyo plan fue generado automáticamente, se elimina también ese plan (y sus asistencias), siempre que no tenga otras comidas asociadas. Editar la comida actualiza el título y la fecha de su plan automático.
