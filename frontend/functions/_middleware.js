// www.football-predictions.org -> the bare domain, path and query kept. (www is a custom domain on the Pages
// project so it reaches us at all; public/_routes.json keeps the built assets from running this.)
export function onRequest({ request, next }) {
  const url = new URL(request.url)
  if (url.hostname !== 'www.football-predictions.org') return next()
  url.protocol = 'https:'
  url.hostname = 'football-predictions.org'
  return Response.redirect(url.toString(), 301)
}
