// Standalone product routes. Keep legacy decision links working without a second tab UI.
const VIEWS=new Set(['home','overview','replay','stats','lineup','squads','settings','decisions']);
export function resolveView(query,fallback='home') {
  const params=query instanceof URLSearchParams?query:new URLSearchParams(query);
  if(params.get('view')==='stats'&&params.get('analysis')==='decisions')return 'decisions';
  return VIEWS.has(params.get('view'))?params.get('view'):fallback;
}
export function viewURL(current,view) {
  if(!VIEWS.has(view))throw Error('Unknown product view');
  const url=new URL(current);url.searchParams.set('view',view);url.searchParams.delete('analysis');return url;
}
