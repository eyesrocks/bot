function setupData(){
    fetch('/statusapi')
        .then(response => response.json())
        .then(data => {
            if (data === 'OFFLINE') {
            window.location.href = "status.html";
            return;
            }
            usercount = 0;
            servercount = 0;
            data.forEach(cluster => {
                cluster.forEach(shard => {
                    usercount += shard.users;
                    servercount += shard.servers;
                });
            });
            //set user info class paragraph
            document.getElementsByClassName('user-info')[0].innerHTML = `serving <span class="highlight">${usercount}</span> users across <span class="highlight">${servercount}</span> servers`;
        });
}
setupData();