<script>
    var botui = new BotUI('botui-app');

    botui.message.add({
        content: 'Hello! How can I assist you today?'
    }).then(function() {
        return botui.action.text({
            action: {
                placeholder: 'Type your question here...'
            }
        });
    }).then(function(res) {
        // Here you can handle the user's input and respond accordingly
        botui.message.add({
            content: 'You said: ' + res.value
        });
    });
</script>