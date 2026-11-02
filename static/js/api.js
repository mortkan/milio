/** Cliente mínimo de la API REST. */

export class ApiError extends Error {
  constructor(message, status = 0, data = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
    this.validationErrors = data?.errors || [];
  }
}

function extractMessage(data, status) {
  if (!data) {
    return `HTTP ${status}`;
  }
  if (typeof data.detail === "string") {
    return data.detail;
  }
  if (Array.isArray(data.detail) && data.detail.length) {
    return data.detail.map((item) => item.msg || String(item)).join(" · ");
  }
  if (Array.isArray(data.errors) && data.errors.length) {
    return data.errors.map((item) => item.msg || String(item)).join(" · ");
  }
  return `HTTP ${status}`;
}

async function request(path, options = {}) {
  const headers = {
    Accept: "application/json",
    ...(options.headers || {}),
  };
  let body = options.body;
  if (body !== undefined && body !== null && typeof body !== "string") {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(path, { ...options, headers, body });
  } catch (error) {
    throw new ApiError("network", 0, null);
  }

  if (response.status === 204) {
    return null;
  }

  let data = null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  } else {
    try {
      data = await response.text();
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    throw new ApiError(extractMessage(data, response.status), response.status, data);
  }
  return data;
}

export const api = {
  request,
  get(path) {
    return request(path);
  },
  post(path, body) {
    return request(path, { method: "POST", body });
  },
  put(path, body) {
    return request(path, { method: "PUT", body });
  },
  patch(path, body) {
    return request(path, { method: "PATCH", body });
  },
  delete(path) {
    return request(path, { method: "DELETE" });
  },
};

export function buildQuery(params) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  });
  const query = search.toString();
  return query ? `?${query}` : "";
}
