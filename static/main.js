document.getElementById('inputForm').addEventListener('submit', function(event) {
    event.preventDefault();  // Prevent the default form submission

    const userInput = document.getElementById('userInput').value;

    fetch('/process', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ input: userInput })
    })
    .then(response => response.json())
    .then(data => {
        document.getElementById('response').innerText = data.response;
    })
    .catch(error => console.error('Error:', error));
});
body {
    font-family: Arial, sans-serif;
    margin: 20px;
    padding: 20px;
    background-color: #f4f4f4;
}

nav {
    margin-bottom: 20px;
}

nav a {
    margin-right: 15px;
    text-decoration: none;
    color: #007BFF;
}

.container {
    background: white;
    padding: 20px;
    border-radius: 5px;
    box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
}

h2 {
    color: #333;
}

form div {
    margin-bottom: 15px;
}

form input {
    padding: 10px;
    width: 100%;
    box-sizing: border-box;
}

form input[type="submit"] {
    background-color: #007BFF;
    color: white;
    border: none;
    cursor: pointer;
}

form input[type="submit"]:hover {
    background-color: #0056b3;
}