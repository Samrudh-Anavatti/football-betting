import { onRequestGet as __match__id__js_onRequestGet } from "C:\\Users\\samru\\Downloads\\football-betting\\frontend\\functions\\match\\[id].js"

export const routes = [
    {
      routePath: "/match/:id",
      mountPath: "/match",
      method: "GET",
      middlewares: [],
      modules: [__match__id__js_onRequestGet],
    },
  ]