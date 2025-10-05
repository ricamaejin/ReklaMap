// Navigation utility functions for staff/admin role management

async function getCurrentUser() {
    try {
        const response = await fetch('/admin/current-user');
        if (response.ok) {
            const user = await response.json();
            console.log('Current user:', user); // Debug log
            return user;
        }
        console.log('Failed to get current user, response not ok');
        return null;
    } catch (error) {
        console.error('Error fetching current user:', error);
        return null;
    }
}

function isStaffMember(userName) {
    const staffNames = ['Alberto Nonato Jr.', 'Maybelen Jamorawon', 'Agnes Bartolome'];
    const isStaff = staffNames.includes(userName);
    console.log('Checking if staff member:', userName, 'Result:', isStaff); // Debug log
    return isStaff;
}

async function setupNavigation() {
    console.log('Setting up navigation...'); // Debug log
    
    const user = await getCurrentUser();
    if (!user) {
        console.log('No user found, cannot setup navigation');
        return;
    }
    
    const navMenu = document.querySelector('.nav-menu');
    if (!navMenu) {
        console.log('Nav menu element not found');
        return;
    }
    
    const isStaff = isStaffMember(user.name);
    const currentPath = window.location.pathname;
    
    console.log('User is staff:', isStaff, 'Current path:', currentPath); // Debug log
    
    if (isStaff) {
        // Staff navigation - only show Complaints
        const isComplaintActive = currentPath.includes('/staff/complaints') || currentPath.includes('/complaints/details');
        console.log('Setting up staff navigation, complaint active:', isComplaintActive);
        navMenu.innerHTML = `
            <a href="/staff/complaints/assigned" class="nav-item ${isComplaintActive ? 'active' : ''}">Complaints</a>
        `;
    } else {
        // Admin navigation - show all tabs
        const isMapActive = currentPath.includes('/map/');
        const isComplaintActive = currentPath.includes('/complaints/') || currentPath.includes('/complaints/details');
        const isDatabaseActive = currentPath.includes('/database/');
        
        console.log('Setting up admin navigation');
        navMenu.innerHTML = `
            <a href="/admin/map/index.html" class="nav-item ${isMapActive ? 'active' : ''}">Map</a>
            <a href="/admin/complaints/all.html" class="nav-item ${isComplaintActive ? 'active' : ''}">Complaints</a>
            <a href="/admin/database/beneficiaries.html" class="nav-item ${isDatabaseActive ? 'active' : ''}">Database</a>
        `;
    }
}

// Initialize navigation on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, setting up navigation');
    setupNavigation();
});

// Also try to setup navigation immediately if DOM is already loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupNavigation);
} else {
    setupNavigation();
}