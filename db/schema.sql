CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    username VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    password VARCHAR(255) NOT NULL,
    role VARCHAR(32) NOT NULL DEFAULT 'guest',
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_users_username (username),
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Separate from users: Silence's public register endpoint accepts user columns.
-- This prevents new accounts from assigning themselves an arbitrary avatar file.
CREATE TABLE IF NOT EXISTS user_avatars (
    user_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    filename CHAR(37) NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS pernoctaciones (
    pernoctacion_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    usuario_id BIGINT UNSIGNED NOT NULL,
    fecha DATE NOT NULL,
    notas VARCHAR(255),
    estado ENUM('pendiente', 'aprobada', 'rechazada') NOT NULL DEFAULT 'pendiente',
    validado_por BIGINT UNSIGNED NULL,
    fecha_validacion DATETIME NULL,
    UNIQUE KEY uq_pernoctaciones_usuario_fecha (usuario_id, fecha),
    FOREIGN KEY (usuario_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (validado_por) REFERENCES users(user_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- One request can represent several earlier nights whose exact dates are unknown.
-- fecha_referencia is not a claim that all nights happened on that day.
CREATE TABLE IF NOT EXISTS ajustes_pernoctaciones (
    ajuste_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    usuario_id BIGINT UNSIGNED NOT NULL,
    fecha_referencia DATE NOT NULL,
    cantidad TINYINT UNSIGNED NOT NULL,
    motivo VARCHAR(255) NOT NULL,
    estado ENUM('pendiente', 'aprobada', 'rechazada') NOT NULL DEFAULT 'pendiente',
    validado_por BIGINT UNSIGNED NULL,
    fecha_validacion DATETIME NULL,
    UNIQUE KEY uq_ajustes_usuario_referencia (usuario_id, fecha_referencia),
    CONSTRAINT chk_ajustes_cantidad CHECK (cantidad BETWEEN 1 AND 31),
    FOREIGN KEY (usuario_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (validado_por) REFERENCES users(user_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS actividades (
    actividad_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    titulo VARCHAR(100) NOT NULL,
    descripcion TEXT,
    fecha_hora DATETIME NOT NULL,
    lugar VARCHAR(100) NOT NULL DEFAULT 'En el piso',
    creado_por BIGINT UNSIGNED NOT NULL,
    generada_por_comida TINYINT(1) NOT NULL DEFAULT 0,
    FOREIGN KEY (creado_por) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS comidas_especiales (
    comida_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    actividad_id BIGINT UNSIGNED NOT NULL,
    nombre_evento VARCHAR(100) NOT NULL,
    menu_platos TEXT NOT NULL,
    coste_total DECIMAL(8,2) NOT NULL DEFAULT 0.00,
    fecha DATETIME NOT NULL,
    FOREIGN KEY (actividad_id) REFERENCES actividades(actividad_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS asistencias (
    asistencia_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    actividad_id BIGINT UNSIGNED NOT NULL,
    usuario_id BIGINT UNSIGNED NOT NULL,
    estado ENUM('confirmado', 'pendiente', 'rechazado') NOT NULL DEFAULT 'confirmado',
    UNIQUE KEY uq_asistencias_actividad_usuario (actividad_id, usuario_id),
    FOREIGN KEY (actividad_id) REFERENCES actividades(actividad_id) ON DELETE CASCADE,
    FOREIGN KEY (usuario_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
