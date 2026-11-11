# Piso Gay — despliegue y desarrollo

## Despliegue en el VPS (`piso.juegosmasids.es`)

1. Comprueba que el registro **A** de `piso.juegosmasids.es` apunta a la IP pública del VPS. Si hay un registro AAAA, también debe apuntar al servidor o eliminarse. Permite conexiones entrantes TCP **80** y **443** en el firewall del proveedor y del VPS. Los puertos no deben estar ocupados por otro servidor web.
2. Clona el repositorio en el VPS. Copia `.env.example` a `.env`, reemplaza las contraseñas y genera una nueva `SILENCE_SECRET_KEY` (por ejemplo, `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`). **Nunca subas `.env` al repositorio.**
3. Desde la carpeta del proyecto, arranca los servicios:

```bash
chmod 600 .env
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs caddy --tail=50
```

Abre **https://piso.juegosmasids.es**. Caddy obtiene y renueva el certificado automáticamente y redirige HTTP a HTTPS. Solo Caddy publica 80/443: Nginx, el backend y MariaDB quedan accesibles únicamente entre contenedores. Conserva los volúmenes `mariadb_data`, `avatar_data`, `caddy_data` y `caddy_config` en tus copias de seguridad.

**Importante antes de publicar en GitHub:** este repositorio ya tenía `.env` registrado en Git, incluso en commits anteriores. Se ha retirado del índice y ahora está en `.gitignore`, pero **sigue en el historial**. Si ese historial llegó a un repositorio remoto, considera las credenciales expuestas. Cambia las contraseñas y la clave de Silence y publica únicamente un historial saneado (o un repositorio nuevo con historial limpio); añadir `.gitignore` no elimina los secretos de commits anteriores. No cambies `DB_PASSWORD` sobre una MariaDB ya inicializada sin actualizar también la contraseña del usuario en la base de datos.

La base existente se conserva: al arrancar, el backend crea las tablas nuevas si faltan y cambia el valor por defecto del rol a `guest`, sin modificar los usuarios `resident` anteriores. **No uses `docker compose down -v`** si quieres conservar datos ni certificados.

## Desarrollo local

No arranques el Compose de producción en tu equipo: intentaría solicitar un certificado para el dominio del VPS. Usa el fichero adicional para conservar `http://localhost:8080` y la API en `http://localhost:8000/api`:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

La web guarda el token de sesión en `localStorage`. HTTPS protege el transporte, pero antes de considerar el servicio endurecido para Internet revisa las dependencias antiguas de Silence y la política de seguridad de sus tokens.

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
