var amqp = require('amqp-connection-manager-rpcx');

var QUEUE_NAME = 'RPC-test'

console.info('\n launch clients:\n');
// Create a new connection manager
var connection = amqp.connect(['amqp://localhost'], {json: true});
connection.on('connect', function() {
    console.log('Connected!');
});
connection.on('disconnect', function(params) {
    console.log('Disconnected.', params.err.stack);
});

// Setup a channel for RPC requests.
const ttl = 60; // Time to live for RPC request (seconds). 0 - infinite
var channelWrapper = connection.createRPCClient(QUEUE_NAME, ttl);



console.log("Connected to RPC channel");

channelWrapper.waitForConnect()
.then(async function() {
    console.log("Connected to RPC channel");

    let req = {};
    try{
        let prc_reply = await channelWrapper.sendRPC(req,ttl, 'data_1.api.data-agent.test-agent', 'data_1.api.data-agent.test-agent::do_something');
        console.log("RPC reply: ", prc_reply);
    } catch (err) {
        console.log("RPC error: ", err);
    }
});
