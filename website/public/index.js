
  document.addEventListener('DOMContentLoaded', function () {
    const button = document.querySelector('.object');
    const lineSegments = {
      top: document.querySelector('.line-segment.top'),
      right: document.querySelector('.line-segment.right'),
      bottom: document.querySelector('.line-segment.bottom'),
      left: document.querySelector('.line-segment.left')
    };

    // Animation to move the lines around the button
    function animateBorder() {
      // Animate top line segment
      anime({
        targets: lineSegments.top,
        width: '100%',
        opacity: [0, 1],
        easing: 'linear',
        duration: 1000,
        loop: true,
        direction: 'normal',
        begin: () => {
          // Reset the position for top line before each loop
          lineSegments.top.style.opacity = 0;
          lineSegments.top.style.width = '0';
        },
        complete: () => {
          lineSegments.top.style.opacity = 0;
        }
      });

      // Animate right line segment
      anime({
        targets: lineSegments.right,
        height: '100%',
        opacity: [0, 1],
        easing: 'linear',
        duration: 1000,
        loop: true,
        direction: 'normal',
        begin: () => {
          lineSegments.right.style.opacity = 0;
          lineSegments.right.style.height = '0';
        },
        complete: () => {
          lineSegments.right.style.opacity = 0;
        }
      });

      // Animate bottom line segment
      anime({
        targets: lineSegments.bottom,
        width: '100%',
        opacity: [0, 1],
        easing: 'linear',
        duration: 1000,
        loop: true,
        direction: 'normal',
        begin: () => {
          lineSegments.bottom.style.opacity = 0;
          lineSegments.bottom.style.width = '0';
        },
        complete: () => {
          lineSegments.bottom.style.opacity = 0;
        }
      });

      // Animate left line segment
      anime({
        targets: lineSegments.left,
        height: '100%',
        opacity: [0, 1],
        easing: 'linear',
        duration: 1000,
        loop: true,
        direction: 'normal',
        begin: () => {
          lineSegments.left.style.opacity = 0;
          lineSegments.left.style.height = '0';
        },
        complete: () => {
          lineSegments.left.style.opacity = 0;
        }
      });
    }

    // Trigger the animation on hover
    button.addEventListener('mouseenter', () => {
      animateBorder();
    });

    button.addEventListener('mouseleave', () => {
      // Stop animation by clearing styles
      anime.remove(lineSegments.top);
      anime.remove(lineSegments.right);
      anime.remove(lineSegments.bottom);
      anime.remove(lineSegments.left);

      // Reset lines to initial state
      lineSegments.top.style.opacity = 0;
      lineSegments.top.style.width = '0';
      lineSegments.right.style.opacity = 0;
      lineSegments.right.style.height = '0';
      lineSegments.bottom.style.opacity = 0;
      lineSegments.bottom.style.width = '0';
      lineSegments.left.style.opacity = 0;
      lineSegments.left.style.height = '0';
    });
  });

