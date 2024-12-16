window.addEventListener('load', function () {
    setTimeout(function () {
        
        document.getElementById('preloader').style.display = 'none';

        document.querySelector('nav').classList.remove('hidden');
        document.querySelector('.hero').classList.remove('hidden');
        document.querySelector('.categories-container').classList.remove('hidden');
        document.querySelector('.main-content').classList.remove('hidden');
        document.querySelector('footer').classList.remove('hidden');
        document.querySelector('#backToTop').classList.remove('hidden');
    }, 2000);
});