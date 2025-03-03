document.addEventListener("DOMContentLoaded", function () {
  const menuImgContainer = document.querySelector(".menu-img");
  const images = document.querySelectorAll(".menu-img img");
  let mouse = { x: 0, y: 0 };
  let cx = window.innerWidth / 2;
  let cy = window.innerHeight / 2;

  const scales = [0.81, 0.84, 0.87, 0.9];

  function update() {
    let dx = mouse.x - cx;
    let dy = mouse.y - cy;

    let tiltx = (dy / cy) * 20;
    let tilty = (dx / cx) * 20;

    gsap.to(menuImgContainer, {
      duration: 2,
      transform: `rotate3d(${tiltx}, ${tilty}, 0, 15deg)`,
      ease: "power3.out",
    });

    images.forEach((img, index) => {
      let parallaxX = -(dx * (index + 1)) / 100;
      let parallaxY = -(dy * (index + 1)) / 100;

      let transformStyles = `translate(calc(-50% + ${parallaxX}px), calc(-50% + ${parallaxY}px)) scale(${scales[index]})`;
      gsap.to(img, {
        duration: 2,
        transform: transformStyles,
        ease: "power3.out",
      });
    });
  }

  document.body.addEventListener("mousemove", function (event) {
    mouse.x = event.clientX;
    mouse.y = event.clientY;
    update();
  });

  window.addEventListener("resize", function () {
    cx = window.innerWidth / 2;
    cy = window.innerHeight / 2;
  });
});
