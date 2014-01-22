# Qualification CS Games 2014

Vous pouvez retrouver toute l'information sur les qualifications dans les documents à [cette adresse](https://drive.google.com/folderview?id=0B6o3r17jd6MXazJkY1p4SkNHcFk&usp=sharing).

 * **Épreuve pratique**: Document avec les instructions pour le défi pratique
 * **Liste de tâches**: Tableurs avec la liste des tâches à effectuer pour chaque partie du défi

## Exécution du serveur

Le serveur requiert Python 2.7.
Il est possible de l'exécuter directement avec `python2 server.py` ou `./server.py`. Le serveur écoute pour les connexions sur le port 31337.

## WebSocket

Le serveur contient un petit serveur WebSocket intégré qui supporte plus ou moins le RFC pour les WebSocket. Pour le défi, il ne derait pas y avoir de problème, mais si votre navigateur web essaie de trop en demander (Fragmentation, keep-alive à partir de ping), vous risquer d'avoir des problème de communication. Dans le cas où vous éprouvez des problèmes de communication, il est possible d'utiliser un proxy WebSocket vers TCP avec Websockify. Lisez la section suivante pour plus d'information.

Voilà un exemple de code qui devrait fonctionner sur la plupart des navigateurs récents et qui permet de communiquer avec le serveur de chat:

```javascript
c = new WebSocket('ws://localhost:31338')

c.onmessage = function(msg){
    // Handle received messages
    console.log(msg);
}

c.onopen = function(){
    c.send("[dst=server]auth bob bob")
}
```

## WebSockify

Il est possible d'exécuter le serveur et d'accepter les connexion WebSocket à l'aide de [Websockify](https://github.com/kanaka/websockify).

La plupart des distributions Linux ont un paquet `websockify` dans leur repertoire de paquet. Si vous êtes sous Windows, c'est peut-être le temps de penser à garder une machine Linux pas trop loin.

Websockify peut être démarré avec la commande: `websockify 31338 localhost:31337`

Websockify supporte seulement les communications binaires, mais il est facile de convertir un Blob en String avec Javascript:

```javascript
c = new WebSocket('ws://localhost:31338', ['binary', 'base64'])

// Return an handler that convert a blob into a string and pass it to the callback
binaryToTextProxy = function(callback) {
    return function(e) {
        var reader = new FileReader(); 
        reader.readAsText(e.data);
        reader.onload = function() {    // Define an event handler
            var text = reader.result;   // This is the file contents
            callback(text);
        }
    }
}

c.onmessage = binaryToText(function(msg){
    // Handle received messages
    console.log(msg);
})

c.onopen = function(){
    c.send("[dst=server]auth bob bob")
}
```
