"use strict";

const TOKEN_KEY = "piso.sessionToken";
const USER_KEY = "piso.user";
const state = { token: null, user: null, activities: [], meals: [], attendance: new Map(), createType: "noche" };
const avatarCache = new Map();
const avatarUrls = new Set();
const $ = (selector) => document.querySelector(selector);

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function notify(message, error = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.toggle("error", error);
  toast.classList.remove("hidden");
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => toast.classList.add("hidden"), 4500);
}

function saveSession(token, user) {
  state.token = token;
  state.user = user;
  try {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch (_error) {
    notify("El navegador no permite recordar la sesión.", true);
  }
  $("#username-label").textContent = user.username || "Usuario";
  renderHeaderAvatar();
  $("#user-actions").classList.remove("hidden");
  $("#bottom-nav").classList.remove("hidden");
}

function clearSession() {
  state.token = null;
  state.user = null;
  state.activities = [];
  state.meals = [];
  state.attendance.clear();
  avatarCache.clear();
  for (const url of avatarUrls) URL.revokeObjectURL(url);
  avatarUrls.clear();
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  } catch (_error) { /* Storage may be disabled. */ }
  $("#user-actions").classList.add("hidden");
  $("#bottom-nav").classList.add("hidden");
}

async function avatarUrl(userId) {
  const id = Number(userId);
  if (!state.token || !Number.isInteger(id) || id < 1) return null;
  if (id === state.user?.user_id && state.user.has_avatar === false) return null;
  if (!avatarCache.has(id)) {
    const token = state.token;
    const pending = (async () => {
      try {
        const response = await fetch(`/api/users/${id}/avatar`, { headers: { Token: token }, cache: "no-store" });
        if (!response.ok || response.headers.get("Content-Type")?.split(";")[0] !== "image/webp") return null;
        const blob = await response.blob();
        if (state.token !== token || avatarCache.get(id) !== pending) return null;
        const url = URL.createObjectURL(blob);
        avatarUrls.add(url);
        return url;
      } catch (_error) {
        return null;
      }
    })();
    avatarCache.set(id, pending);
  }
  return avatarCache.get(id);
}

function avatarElement(userId, variant = "small") {
  const node = element("span", `avatar avatar-${variant}`, "♥");
  node.setAttribute("aria-hidden", "true");
  const token = state.token;
  void avatarUrl(userId).then((url) => {
    if (!url || state.token !== token || !node.isConnected) return;
    const image = element("img", "");
    image.alt = "";
    image.src = url;
    node.replaceChildren(image);
  });
  return node;
}

function renderHeaderAvatar() {
  if (!state.user) return;
  const node = avatarElement(state.user.user_id, "header");
  node.id = "header-avatar";
  $("#header-avatar").replaceWith(node);
}

function invalidateAvatar(userId) {
  const id = Number(userId);
  const cached = avatarCache.get(id);
  avatarCache.delete(id);
  if (cached) void cached.then((url) => {
    if (url) {
      URL.revokeObjectURL(url);
      avatarUrls.delete(url);
    }
  });
}

function refreshOtherAvatars(ids) {
  for (const id of new Set(ids)) {
    if (id !== state.user?.user_id) invalidateAvatar(id);
  }
}

// Silence expects its signed session token in the Token header, not Bearer.
async function apiFetch(endpoint, method = "GET", data = undefined) {
  const headers = { Accept: "application/json" };
  if (state.token) headers.Token = state.token;
  if (data !== undefined) headers["Content-Type"] = "application/json";

  let response;
  try {
    response = await fetch(`/api/${endpoint.replace(/^\/+/, "")}`, {
      method,
      headers,
      body: data === undefined ? undefined : JSON.stringify(data),
      cache: "no-store",
    });
  } catch (_error) {
    throw new ApiError("No se pudo conectar. Comprueba tu conexión e inténtalo de nuevo.", 0);
  }

  const result = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && state.token) {
      clearSession();
      navigate("auth");
      throw new ApiError("Tu sesión ha caducado. Vuelve a entrar.", 401);
    }
    throw new ApiError(result?.message || `Error del servidor (${response.status}).`, response.status);
  }
  return result;
}

function navigate(viewName) {
  const view = state.token && ["planes", "ranking", "crear", "profile"].includes(viewName) ? viewName : "auth";
  for (const section of document.querySelectorAll("main > section.view")) {
    section.classList.toggle("hidden", section.id !== `view-${view}`);
  }
  for (const button of document.querySelectorAll("#bottom-nav button")) {
    const active = button.dataset.view === view;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  window.scrollTo({ top: 0, behavior: "auto" });
  if (view === "planes") void loadPlans();
  if (view === "ranking") void loadRanking();
  if (view === "crear") { showCreate(state.createType); void loadNights(); }
  if (view === "profile") void loadProfile();
}

function showAuth(register) {
  $("#login-form").classList.toggle("hidden", register);
  $("#register-form").classList.toggle("hidden", !register);
  $("#show-login").classList.toggle("selected", !register);
  $("#show-register").classList.toggle("selected", register);
  $("#show-login").setAttribute("aria-pressed", String(!register));
  $("#show-register").setAttribute("aria-pressed", String(register));
}

function showCreate(type) {
  state.createType = type;
  for (const button of document.querySelectorAll("[data-create]")) {
    const selected = button.dataset.create === type;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  }
  $("#night-guest").classList.toggle("hidden", type !== "noche" || state.user?.role === "resident");
  $("#night-host").classList.toggle("hidden", type !== "noche" || state.user?.role !== "resident");
  $("#create-activity").classList.toggle("hidden", type !== "actividad");
  $("#create-meal").classList.toggle("hidden", type !== "comida");
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function empty(container, message) {
  container.replaceChildren(element("div", "empty-state", message));
}

function formatDate(value, withTime = true) {
  if (!value) return "Sin fecha";
  const [dayPart, timePart] = value.split("T");
  const [year, month, day] = dayPart.split("-");
  if (!year || !month || !day) return value;
  return `${day}/${month}/${year}${withTime && timePart ? ` · ${timePart.slice(0, 5)}` : ""}`;
}

function card(title, label, labelClass = "") {
  const article = element("article", "event-card");
  if (labelClass === "badge-meal") article.classList.add("event-card--meal");
  const top = element("div", "card-top");
  top.append(element("span", `badge ${labelClass}`, label));
  article.append(top, element("h3", "", title));
  return article;
}

function metadata(article, ...items) {
  const meta = element("div", "card-meta");
  for (const item of items.filter(Boolean)) meta.append(element("span", "", item));
  article.append(meta);
}

async function act(button, callback) {
  button.disabled = true;
  try {
    await callback();
  } catch (error) {
    notify(error.message || "No se pudo completar la operación.", true);
  } finally {
    button.disabled = false;
  }
}

function renderPlans() {
  const activitiesList = $("#activities-list");
  const mealsList = $("#meals-list");
  activitiesList.replaceChildren();
  mealsList.replaceChildren();
  const visibleActivities = state.activities.filter((activity) => !activity.generada_por_comida);
  $("#activities-count").textContent = String(visibleActivities.length);
  $("#meals-count").textContent = String(state.meals.length);

  const attendanceButton = (article, activityId) => {
    const attendees = state.attendance.get(activityId) || [];
    const confirmed = attendees.filter((person) => person.estado === "confirmado");
    const attending = confirmed.some((person) => person.usuario_id === state.user.user_id);
    if (confirmed.length) {
      const people = element("div", "attendance-people");
      people.append(element("span", "attendance-label", `${confirmed.length} ${confirmed.length === 1 ? "persona apuntada" : "personas apuntadas"}`));
      for (const person of confirmed) {
        const attendee = element("span", "attendee");
        attendee.append(avatarElement(person.usuario_id), element("span", "attendee-name", person.username));
        people.append(attendee);
      }
      article.append(people);
    }
    const button = element("button", `button ${attending ? "button-light" : "button-primary"}`, attending ? "✓ Apuntado · cancelar" : "＋ Me apunto");
    button.type = "button";
    button.addEventListener("click", () => act(button, async () => {
      if (attending) {
        await apiFetch(`actividades/${activityId}/asistencia`, "DELETE");
        notify("Has cancelado tu asistencia.");
      } else {
        await apiFetch(`actividades/${activityId}/asistencia`, "POST", { estado: "confirmado" });
        notify("¡Ya estás apuntado!");
      }
      await loadPlans();
    }));
    article.append(button);
  };

  for (const activity of visibleActivities) {
    const item = card(activity.titulo, "PLAN");
    metadata(item, `◷ ${formatDate(activity.fecha_hora)}`, `⌖ ${activity.lugar}`);
    if (activity.descripcion) item.append(element("p", "", activity.descripcion));
    attendanceButton(item, activity.actividad_id);
    activitiesList.append(item);
  }
  for (const meal of state.meals) {
    const item = card(meal.nombre_evento, "COMIDA", "badge-meal");
    metadata(item, `◷ ${formatDate(meal.fecha)}`, `${meal.coste_total} €`);
    item.append(element("p", "", meal.menu_platos));
    attendanceButton(item, meal.actividad_id);
    mealsList.append(item);
  }
  if (!visibleActivities.length) empty(activitiesList, "Aún no hay planes independientes. ¡Propón el primero en Nuevo!");
  if (!state.meals.length) empty(mealsList, "No hay comidas especiales todavía.");
}

async function loadPlans() {
  if (!state.token) return;
  const token = state.token;
  try {
    const [activities, meals] = await Promise.all([apiFetch("actividades"), apiFetch("comidas")]);
    if (token !== state.token) return;
    const attendance = await Promise.all(activities.map(async (activity) => {
      const guests = await apiFetch(`actividades/${activity.actividad_id}/asistencias`);
      return [activity.actividad_id, guests];
    }));
    if (token !== state.token) return;
    state.activities = activities;
    state.meals = meals;
    state.attendance = new Map(attendance);
    refreshOtherAvatars(attendance.flatMap(([, people]) => people.map((person) => person.usuario_id)));
    renderPlans();
  } catch (error) {
    if (state.token) notify(error.message, true);
  }
}

async function loadRanking() {
  if (!state.token) return;
  const token = state.token;
  try {
    const rows = await apiFetch("ranking/pernoctaciones");
    if (token !== state.token) return;
    refreshOtherAvatars(rows.map((person) => person.usuario_id));
    const podium = $("#ranking-podium");
    const restHeading = $("#ranking-rest-heading");
    const list = $("#ranking-list");
    podium.replaceChildren();
    list.replaceChildren();
    podium.classList.toggle("hidden", !rows.length);
    restHeading.classList.toggle("hidden", rows.length <= 3);
    list.classList.toggle("hidden", rows.length > 0 && rows.length <= 3);
    if (!rows.length) {
      const item = element("li", "empty-state", "Todavía no hay noches aprobadas. ¡El ranking está por escribir!");
      list.append(item);
      return;
    }
    const podiumSlots = ["first", "second", "third"];
    rows.slice(0, 3).forEach((row, index) => {
      const entry = element("div", `podium-entry podium-entry--${podiumSlots[index]}`);
      entry.dataset.position = String(row.posicion);
      entry.setAttribute("role", "listitem");
      entry.setAttribute("aria-label", `${row.username}, puesto ${row.posicion}, ${row.noches} ${row.noches === 1 ? "noche" : "noches"}`);
      const person = element("div", "podium-person");
      const name = element("strong", "podium-name", row.username);
      name.title = row.username;
      person.append(avatarElement(row.usuario_id, "podium"), name,
        element("span", "podium-nights", `${row.noches} ${row.noches === 1 ? "noche" : "noches"}`));
      const step = element("div", "podium-step");
      step.append(element("span", "podium-number", String(row.posicion)));
      entry.append(person, step);
      podium.append(entry);
    });
    for (const row of rows.slice(3)) {
      const item = element("li", "rank-row");
      item.dataset.position = String(row.posicion);
      const score = element("span", "rank-nights", String(row.noches));
      score.append(element("small", "", row.noches === 1 ? "noche" : "noches"));
      const identity = element("span", "rank-identity");
      identity.append(avatarElement(row.usuario_id), element("span", "rank-name", row.username));
      item.append(element("span", "rank-position", String(row.posicion)), identity, score);
      list.append(item);
    }
  } catch (error) {
    if (state.token) notify(error.message, true);
  }
}

function renderProfile() {
  if (!state.user) return;
  $("#profile-name").textContent = state.user.username;
  $("#profile-role").textContent = state.user.role === "resident" ? "Anfitrión del piso" : "Invitado del piso";
  $("#delete-avatar").classList.toggle("hidden", !state.user.has_avatar);
  const node = avatarElement(state.user.user_id, "large");
  node.id = "profile-avatar";
  $("#profile-avatar").replaceWith(node);
}

async function loadProfile() {
  if (!state.token) return;
  const token = state.token;
  try {
    const profile = await apiFetch("users/me");
    if (token !== state.token) return;
    state.user = { ...state.user, role: profile.role, has_avatar: Boolean(profile.has_avatar) };
    invalidateAvatar(state.user.user_id);
    try { localStorage.setItem(USER_KEY, JSON.stringify(state.user)); } catch (_error) { /* Storage disabled. */ }
    renderHeaderAvatar();
    renderProfile();
  } catch (error) {
    if (state.token) notify(error.message, true);
  }
}

async function uploadAvatar(file) {
  if (file.size > 2 * 1024 * 1024) throw new ApiError("La foto no puede superar los 2 MB.", 413);
  if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) throw new ApiError("Elige una imagen JPG, PNG o WebP.", 400);
  const form = new FormData();
  form.append("avatar", file);
  let response;
  try {
    response = await fetch("/api/users/me/avatar", { method: "POST", headers: { Token: state.token }, body: form, cache: "no-store" });
  } catch (_error) {
    throw new ApiError("No se pudo subir la foto. Comprueba tu conexión.", 0);
  }
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    if (response.status === 401) {
      clearSession();
      navigate("auth");
      throw new ApiError("Tu sesión ha caducado. Vuelve a entrar.", 401);
    }
    throw new ApiError(error?.message || "No se pudo guardar la foto.", response.status);
  }
  invalidateAvatar(state.user.user_id);
  state.user.has_avatar = true;
  try { localStorage.setItem(USER_KEY, JSON.stringify(state.user)); } catch (_error) { /* Storage disabled. */ }
  renderHeaderAvatar();
  renderProfile();
}

async function loadNights() {
  if (!state.token) return;
  const token = state.token;
  try {
    const [rows, adjustments] = await Promise.all([
      apiFetch("pernoctaciones"),
      apiFetch("ajustes-pernoctaciones"),
    ]);
    if (token !== state.token) return;
    const host = state.user?.role === "resident";
    const list = host ? $("#pending-nights") : $("#my-nights");
    list.replaceChildren();
    const visible = host ? rows.filter((night) => night.estado === "pendiente") : rows;
    if (!visible.length) {
      empty(list, host ? "No hay noches pendientes. Todo al día." : "Aún no has apuntado ninguna noche.");
    }
    for (const night of visible) {
      const item = card(host ? night.username : formatDate(night.fecha, false), night.estado.toUpperCase(), night.estado === "pendiente" ? "badge-pending" : "");
      metadata(item, host ? formatDate(night.fecha, false) : `Estado: ${night.estado}`);
      if (night.notas) item.append(element("p", "", night.notas));
      if (host) {
        const actions = element("div", "card-actions");
        for (const [label, value, style] of [["Aprobar", "aprobada", "button-light"], ["Rechazar", "rechazada", "button-danger"]]) {
          const button = element("button", `button ${style}`, label);
          button.type = "button";
          button.addEventListener("click", () => act(button, async () => {
            await apiFetch(`pernoctaciones/${night.pernoctacion_id}/validacion`, "PUT", { estado: value });
            notify(`Noche ${value}.`);
            await loadNights();
          }));
          actions.append(button);
        }
        item.append(actions);
      }
      list.append(item);
    }
    renderHistoricalAdjustments(adjustments, host);
  } catch (error) {
    if (state.token) notify(error.message, true);
  }
}

function renderHistoricalAdjustments(adjustments, host) {
  const list = host ? $("#pending-adjustments") : $("#my-adjustments");
  list.replaceChildren();
  const visible = host ? adjustments.filter((item) => item.estado === "pendiente") : adjustments;
  if (!visible.length) {
    empty(list, host ? "No hay ajustes históricos pendientes." : "Todavía no has solicitado noches históricas.");
    return;
  }
  for (const adjustment of visible) {
    const title = `${adjustment.cantidad} ${adjustment.cantidad === 1 ? "noche" : "noches"} históricas`;
    const item = card(host ? adjustment.username : title, adjustment.estado.toUpperCase(), adjustment.estado === "pendiente" ? "badge-pending" : "");
    item.classList.add("event-card--history");
    metadata(item, host ? title : `Estado: ${adjustment.estado}`, `Referencia: ${formatDate(adjustment.fecha_referencia, false)}`);
    item.append(element("p", "", adjustment.motivo));
    if (host) {
      const actions = element("div", "card-actions");
      for (const [label, value, style] of [["Aprobar", "aprobada", "button-light"], ["Rechazar", "rechazada", "button-danger"]]) {
        const button = element("button", `button ${style}`, label);
        button.type = "button";
        button.addEventListener("click", () => act(button, async () => {
          await apiFetch(`ajustes-pernoctaciones/${adjustment.ajuste_id}/validacion`, "PUT", { estado: value });
          notify(`Ajuste histórico ${value}.`);
          await loadNights();
        }));
        actions.append(button);
      }
      item.append(actions);
    } else if (adjustment.estado !== "aprobada") {
      const actions = element("div", "card-actions");
      if (adjustment.estado === "rechazada") {
        const retry = element("button", "button button-light", "Reenviar");
        retry.type = "button";
        retry.addEventListener("click", () => act(retry, async () => {
          await apiFetch(`ajustes-pernoctaciones/${adjustment.ajuste_id}`, "PUT", {});
          notify("Ajuste reenviado para validar.");
          await loadNights();
        }));
        actions.append(retry);
      }
      const remove = element("button", "button button-danger", "Eliminar");
      remove.type = "button";
      remove.addEventListener("click", () => act(remove, async () => {
        await apiFetch(`ajustes-pernoctaciones/${adjustment.ajuste_id}`, "DELETE");
        notify("Solicitud eliminada.");
        await loadNights();
      }));
      actions.append(remove);
      item.append(actions);
    }
    list.append(item);
  }
}

function setHistoricalReference() {
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  const pad = (number) => String(number).padStart(2, "0");
  $("#historical-form [name=fecha_referencia]").value = `${yesterday.getFullYear()}-${pad(yesterday.getMonth() + 1)}-${pad(yesterday.getDate())}`;
}

function onForm(selector, handler) {
  $(selector).addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) return;
    const button = form.querySelector('button[type="submit"]');
    await act(button, async () => {
      await handler(Object.fromEntries(new FormData(form)), form);
    });
  });
}

function init() {
  $("#show-login").addEventListener("click", () => showAuth(false));
  $("#show-register").addEventListener("click", () => showAuth(true));
  $("#profile-button").addEventListener("click", () => navigate("profile"));
  $("#logout-button").addEventListener("click", () => { clearSession(); navigate("auth"); notify("Sesión cerrada."); });
  for (const button of document.querySelectorAll("#bottom-nav button")) button.addEventListener("click", () => navigate(button.dataset.view));
  for (const button of document.querySelectorAll("[data-create]")) button.addEventListener("click", () => showCreate(button.dataset.create));
  $("#refresh-planes").addEventListener("click", () => void loadPlans());
  $("#refresh-ranking").addEventListener("click", () => void loadRanking());
  $("#avatar-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const file = form.elements.avatar.files[0];
    if (!file || !form.reportValidity()) return;
    const button = form.querySelector('button[type="submit"]');
    await act(button, async () => {
      await uploadAvatar(file);
      form.reset();
      notify("¡Foto de perfil actualizada!");
    });
  });
  $("#delete-avatar").addEventListener("click", (event) => act(event.currentTarget, async () => {
    await apiFetch("users/me/avatar", "DELETE");
    invalidateAvatar(state.user.user_id);
    state.user.has_avatar = false;
    try { localStorage.setItem(USER_KEY, JSON.stringify(state.user)); } catch (_error) { /* Storage disabled. */ }
    renderHeaderAvatar();
    renderProfile();
    notify("Foto eliminada.");
  }));

  onForm("#login-form", async (data) => {
    const result = await apiFetch("login", "POST", data);
    saveSession(result.sessionToken, result.user);
    navigate("planes");
    notify(`¡Bienvenido, ${result.user.username}!`);
  });
  onForm("#register-form", async (data) => {
    const result = await apiFetch("register", "POST", data);
    saveSession(result.sessionToken, result.user);
    navigate("planes");
    notify("Cuenta creada. ¡Bienvenido al piso!");
  });
  onForm("#night-form", async (data, form) => {
    await apiFetch("pernoctaciones", "POST", { fecha: data.fecha, notas: data.notas || null });
    form.reset();
    notify("Noche enviada para validar.");
    await loadNights();
  });
  onForm("#historical-form", async (data, form) => {
    await apiFetch("ajustes-pernoctaciones", "POST", {
      fecha_referencia: data.fecha_referencia,
      cantidad: Number(data.cantidad),
      motivo: data.motivo,
    });
    form.reset();
    setHistoricalReference();
    notify("Ajuste histórico enviado para validar.");
    await loadNights();
  });
  onForm("#activity-form", async (data, form) => {
    await apiFetch("actividades", "POST", { titulo: data.titulo, fecha_hora: data.fecha_hora, lugar: data.lugar, descripcion: data.descripcion || null });
    form.reset();
    notify("¡Plan publicado!");
    navigate("planes");
  });
  onForm("#meal-form", async (data, form) => {
    await apiFetch("comidas", "POST", { nombre_evento: data.nombre_evento, menu_platos: data.menu_platos, coste_total: data.coste_total, fecha: data.fecha });
    form.reset();
    notify("¡Comida publicada!");
    navigate("planes");
  });

  setHistoricalReference();

  try {
    const token = localStorage.getItem(TOKEN_KEY);
    const user = JSON.parse(localStorage.getItem(USER_KEY));
    if (token && user?.user_id && user?.username) {
      saveSession(token, user);
      navigate("planes");
      return;
    }
  } catch (_error) { /* Corrupt or unavailable storage; show auth. */ }
  clearSession();
  navigate("auth");
}

document.addEventListener("DOMContentLoaded", init);
