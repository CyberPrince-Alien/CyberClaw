/* CyberClaw Documentation System JS — Interactive Control */

document.addEventListener('DOMContentLoaded', () => {
  // Setup view/tab switcher
  const menuItems = document.querySelectorAll('.menu-item');
  const sections = document.querySelectorAll('.doc-section');
  const viewTitle = document.getElementById('viewTitle');

  menuItems.forEach(item => {
    item.addEventListener('click', () => {
      const targetView = item.getAttribute('data-view');
      if (!targetView) return;

      // Active class changes on sidebar items
      menuItems.forEach(i => i.classList.remove('active'));
      item.classList.add('active');

      // Show/Hide section panels
      sections.forEach(sec => {
        if (sec.id === `section-${targetView}`) {
          sec.classList.add('active');
        } else {
          sec.classList.remove('active');
        }
      });

      // Update header title
      viewTitle.textContent = item.querySelector('.menu-item-text').textContent;

      // Smooth scroll to top of content
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  });

  // Dynamic search system
  const searchInput = document.getElementById('docsSearch');
  searchInput.addEventListener('input', (e) => {
    const query = e.target.value.toLowerCase().trim();
    if (!query) {
      // Clear search: show all normal section titles and menu items
      document.querySelectorAll('.menu-section').forEach(s => s.style.display = 'block');
      menuItems.forEach(item => item.style.display = 'flex');
      return;
    }

    // Iterate through all list items to find matches
    menuItems.forEach(item => {
      const text = item.textContent.toLowerCase();
      if (text.includes(query)) {
        item.style.display = 'flex';
      } else {
        item.style.display = 'none';
      }
    });

    // Hide empty header titles
    document.querySelectorAll('.menu-section').forEach(section => {
      const visibleItems = section.querySelectorAll('.menu-item[style="display: flex;"]');
      if (visibleItems.length === 0) {
        section.style.display = 'none';
      } else {
        section.style.display = 'block';
      }
    });
  });

  // Setup code copy-to-clipboard actions
  setupCodeCopy();
});

function setupCodeCopy() {
  const preBlocks = document.querySelectorAll('pre');
  preBlocks.forEach(pre => {
    // Inject the copy button dynamically
    const copyBtn = document.createElement('button');
    copyBtn.className = 'btn-copy';
    copyBtn.textContent = 'Copy';
    pre.appendChild(copyBtn);

    copyBtn.addEventListener('click', () => {
      const code = pre.querySelector('code').textContent;
      navigator.clipboard.writeText(code).then(() => {
        copyBtn.textContent = 'Copied!';
        copyBtn.style.color = 'var(--accent-cyan)';
        copyBtn.style.borderColor = 'rgba(76, 201, 240, 0.4)';
        
        setTimeout(() => {
          copyBtn.textContent = 'Copy';
          copyBtn.style.color = 'var(--text-dim)';
          copyBtn.style.borderColor = 'var(--border-glass)';
        }, 2000);
      });
    });
  });
}
