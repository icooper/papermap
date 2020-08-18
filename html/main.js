/// <reference path="../node_modules/@types/leaflet/index.d.ts" />

const osm = L.tileLayer('http://{s}.tile.osm.org/{z}/{x}/{y}.png', {attribution: '&copy; <a href="http://osm.org/copyright">OpenStreetMap</a> contributors', minZoom: 0, maxZoom: 22});
const cartodb = L.tileLayer('http://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png', {attribution: '&copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, &copy; <a href="http://cartodb.com/attributions">CartoDB</a>', minZoom: 0, maxZoom: 22});
const toner = L.tileLayer('http://{s}.tile.stamen.com/toner/{z}/{x}/{y}.png', {attribution: 'Map tiles by <a href="http://stamen.com">Stamen Design</a>, under <a href="http://creativecommons.org/licenses/by/3.0">CC BY 3.0</a>. Data by <a href="http://openstreetmap.org">OpenStreetMap</a>, under <a href="http://www.openstreetmap.org/copyright">ODbL</a>.', minZoom: 0, maxZoom: 22});
const white = L.tileLayer('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAQAAAAEAAQMAAABmvDolAAAAA1BMVEX///+nxBvIAAAAH0lEQVQYGe3BAQ0AAADCIPunfg43YAAAAAAAAAAA5wIhAAAB9aK9BAAAAABJRU5ErkJggg==', {minZoom: 0, maxZoom: 22});

let map = L.map('map', {
    center: [37.16690910059701, -101.87611661509155],
    zoom: 14,
    minZoom: 5,
    maxZoom: 14,
    layers: [white]
});

map.on('moveend', function() {
    var center = map.getCenter();
    var zoom = map.getZoom()
    console.log('center', `(${center.lng}, ${center.lat}), zoom=${zoom}`);
})

let basemaps = {
    'OpenStreetMap': osm,
    'CartoDB Positron': cartodb,
    'Stamen Toner': toner,
    'No Basemap': white
}
let layerControl = L.control.layers(basemaps, null, { collapsed: false })
layerControl.addTo(map);

var minx = 180.0,
    miny = 180.0,
    maxx = -180.0,
    maxy = -180.0;

var mapsRequest = new XMLHttpRequest();
mapsRequest.onreadystatechange = function() {
    if (mapsRequest.readyState == 4 && mapsRequest.status == 200) {
        var data = JSON.parse(mapsRequest.responseText);

        // loop through the returned maps
        data.maps.forEach(map => {
            minx = Math.min(minx, map.bounds[0]);
            miny = Math.min(miny, map.bounds[1]);
            maxx = Math.max(maxx, map.bounds[2]);
            maxy = Math.max(maxy, map.bounds[3]);

            
            layerControl.addOverlay(L.tileLayer(map.urlTemplate, { tms: true, opacity: 0.7, attribution: "", minZoom: map.minZoom, maxZoom: map.maxZoom }), map.name);
        });

        // recenter map
        let bounds = [[miny, minx], [maxy, maxx]];
        console.dir(bounds);
        map.fitBounds(bounds);
    }
};
mapsRequest.open('GET', 'http://localhost:8234/maps.json', true);
mapsRequest.send();

// load overlay maps
//layerControl.addOverlay(L.tileLayer('http://localhost:8234/cimarron/{z}/{x}/{y}.png', {tms: true, opacity: 0.7, attribution: "", minZoom: 5, maxZoom: 14}), 'Cimarron');

