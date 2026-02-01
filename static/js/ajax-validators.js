/**
 * System-wide AJAX Validators for Blood Connect
 * Supports: Donors, Nurses, Patients
 * Include this file in signup forms to enable real-time validation
 */

// Debounce helper function
function debounce(func, delay) {
    let timeout;
    return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), delay);
    };
}

// ================================================
// USERNAME VALIDATION (Universal for all users)
// ================================================
function initUsernameValidator(inputId, feedbackId, suggestionsId) {
    const usernameInput = document.getElementById(inputId);
    const usernameFeedback = document.getElementById(feedbackId);
    const usernameSuggestions = document.getElementById(suggestionsId);
    
    if (!usernameInput) return;
    
    // Helper to select a suggestion
    window.selectUsername = function(username) {
        usernameInput.value = username;
        usernameInput.focus();
        checkUsername();
        const serverSuggestions = document.querySelector('.username-suggestions');
        if (serverSuggestions) {
            serverSuggestions.style.display = 'none';
        }
    };
    
    const checkUsername = debounce(function() {
        const username = usernameInput.value.trim();
        
        if (!username) {
            usernameFeedback.textContent = '';
            if (usernameSuggestions) usernameSuggestions.innerHTML = '';
            usernameInput.classList.remove('is-invalid', 'is-valid');
            return;
        }
        
        // Client-side validation first
        if (username.length < 4) {
            usernameFeedback.textContent = '✗ Username must be at least 4 characters';
            usernameFeedback.className = 'validation-feedback validation-error';
            usernameInput.classList.add('is-invalid');
            usernameInput.classList.remove('is-valid');
            return;
        }
        
        if (!/^[\w.@+-]+$/.test(username)) {
            usernameFeedback.textContent = '✗ Username can only contain letters, numbers, and @/./+/-/_ characters';
            usernameFeedback.className = 'validation-feedback validation-error';
            usernameInput.classList.add('is-invalid');
            usernameInput.classList.remove('is-valid');
            return;
        }
        
        usernameFeedback.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Checking...';
        usernameFeedback.className = 'validation-feedback validation-checking';
        
        fetch(`/ajax/check-username/?username=${encodeURIComponent(username)}`)
            .then(response => response.json())
            .then(data => {
                if (data.exists === false) {
                    usernameFeedback.textContent = '✓ ' + data.message;
                    usernameFeedback.className = 'validation-feedback validation-success';
                    usernameInput.classList.remove('is-invalid');
                    usernameInput.classList.add('is-valid');
                    if (usernameSuggestions) usernameSuggestions.innerHTML = '';
                } else {
                    usernameFeedback.textContent = '✗ ' + data.message;
                    usernameFeedback.className = 'validation-feedback validation-error';
                    usernameInput.classList.remove('is-valid');
                    usernameInput.classList.add('is-invalid');
                    
                    if (data.suggestions && data.suggestions.length > 0 && usernameSuggestions) {
                        let suggestionsHTML = `
                            <div class="username-suggestions mt-2">
                                <small class="text-muted"><strong>💡 Try these available usernames:</strong></small>
                                <div class="mt-2">
                        `;
                        data.suggestions.forEach(suggestion => {
                            suggestionsHTML += `
                                <span class="badge bg-primary suggestion-badge me-1"
                                    style="cursor:pointer;"
                                    onclick="selectUsername('${suggestion}')">${suggestion}</span>
                            `;
                        });
                        suggestionsHTML += '</div></div>';
                        usernameSuggestions.innerHTML = suggestionsHTML;
                    }
                }
            })
            .catch(error => {
                console.error('Error checking username:', error);
                usernameFeedback.textContent = '⚠️ Error checking username. Please try again.';
                usernameFeedback.className = 'validation-feedback validation-error';
            });
    }, 500);
    
    usernameInput.addEventListener('input', checkUsername);
}

// ================================================
// EMAIL VALIDATION (Universal for all users)
// ================================================
function initEmailValidator(inputId, feedbackId) {
    const emailInput = document.getElementById(inputId);
    const emailFeedback = document.getElementById(feedbackId);
    
    if (!emailInput) return;
    
    const checkEmail = debounce(function() {
        const email = emailInput.value.trim();
        
        if (!email) {
            emailFeedback.textContent = '';
            emailInput.classList.remove('is-invalid', 'is-valid');
            return;
        }
        
        // Client-side format validation
        const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailPattern.test(email)) {
            emailFeedback.textContent = '✗ Please enter a valid email address';
            emailFeedback.className = 'validation-feedback validation-error';
            emailInput.classList.add('is-invalid');
            emailInput.classList.remove('is-valid');
            return;
        }
        
        emailFeedback.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Checking...';
        emailFeedback.className = 'validation-feedback validation-checking';
        
        fetch(`/ajax/check-email/?email=${encodeURIComponent(email)}`)
            .then(response => response.json())
            .then(data => {
                if (data.valid) {
                    emailFeedback.textContent = '✓ ' + data.message;
                    emailFeedback.className = 'validation-feedback validation-success';
                    emailInput.classList.remove('is-invalid');
                    emailInput.classList.add('is-valid');
                } else {
                    emailFeedback.textContent = '✗ ' + data.message;
                    emailFeedback.className = 'validation-feedback validation-error';
                    emailInput.classList.remove('is-valid');
                    emailInput.classList.add('is-invalid');
                }
            })
            .catch(error => {
                console.error('Error checking email:', error);
                emailFeedback.textContent = '⚠️ Error checking email. Please try again.';
                emailFeedback.className = 'validation-feedback validation-error';
            });
    }, 500);
    
    emailInput.addEventListener('input', checkEmail);
}

// ================================================
// NATIONAL ID VALIDATION (Donor & Patient)
// ================================================
function initNationalIdValidator(inputId, feedbackId) {
    const nationalIdInput = document.getElementById(inputId);
    const nationalIdFeedback = document.getElementById(feedbackId);
    
    if (!nationalIdInput) return;
    
    const checkNationalId = debounce(function() {
        const nationalId = nationalIdInput.value.trim();
        
        if (!nationalId) {
            nationalIdFeedback.textContent = '';
            nationalIdInput.classList.remove('is-invalid', 'is-valid');
            return;
        }
        
        // Client-side validation
        if (nationalId.length !== 8 || !/^\d+$/.test(nationalId)) {
            nationalIdFeedback.textContent = '✗ National ID must be exactly 8 digits';
            nationalIdFeedback.className = 'validation-feedback validation-error';
            nationalIdInput.classList.add('is-invalid');
            nationalIdInput.classList.remove('is-valid');
            return;
        }
        
        nationalIdFeedback.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Checking...';
        nationalIdFeedback.className = 'validation-feedback validation-checking';
        
        fetch(`/ajax/check-national-id/?national_id=${encodeURIComponent(nationalId)}`)
            .then(response => response.json())
            .then(data => {
                if (data.valid) {
                    nationalIdFeedback.textContent = '✓ ' + data.message;
                    nationalIdFeedback.className = 'validation-feedback validation-success';
                    nationalIdInput.classList.remove('is-invalid');
                    nationalIdInput.classList.add('is-valid');
                } else {
                    nationalIdFeedback.textContent = '✗ ' + data.message;
                    nationalIdFeedback.className = 'validation-feedback validation-error';
                    nationalIdInput.classList.remove('is-valid');
                    nationalIdInput.classList.add('is-invalid');
                }
            })
            .catch(error => {
                console.error('Error checking national ID:', error);
                nationalIdFeedback.textContent = '⚠️ Error checking ID. Please try again.';
                nationalIdFeedback.className = 'validation-feedback validation-error';
            });
    }, 500);
    
    nationalIdInput.addEventListener('input', function() {
        // Only allow digits, max 8
        this.value = this.value.replace(/\D/g, '').slice(0, 8);
        checkNationalId();
    });
}

// ================================================
// MOBILE NUMBER VALIDATION (Donor & Patient)
// ================================================
function initMobileValidator(inputId, feedbackId, format = 'donor') {
    const mobileInput = document.getElementById(inputId);
    const mobileFeedback = document.getElementById(feedbackId);
    
    if (!mobileInput) return;
    
    const checkMobile = debounce(function() {
        const mobile = mobileInput.value.trim();
        
        if (!mobile) {
            mobileFeedback.textContent = '';
            mobileInput.classList.remove('is-invalid', 'is-valid');
            return;
        }
        
        mobileFeedback.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Checking...';
        mobileFeedback.className = 'validation-feedback validation-checking';
        
        fetch(`/ajax/check-mobile/?mobile=${encodeURIComponent(mobile)}`)
            .then(response => response.json())
            .then(data => {
                if (data.valid) {
                    mobileFeedback.textContent = '✓ ' + data.message;
                    mobileFeedback.className = 'validation-feedback validation-success';
                    mobileInput.classList.remove('is-invalid');
                    mobileInput.classList.add('is-valid');
                } else {
                    mobileFeedback.textContent = '✗ ' + data.message;
                    mobileFeedback.className = 'validation-feedback validation-error';
                    mobileInput.classList.remove('is-valid');
                    mobileInput.classList.add('is-invalid');
                }
            })
            .catch(error => {
                console.error('Error checking mobile:', error);
                mobileFeedback.textContent = '⚠️ Error checking mobile. Please try again.';
                mobileFeedback.className = 'validation-feedback validation-error';
            });
    }, 500);
    
    mobileInput.addEventListener('input', function() {
        let value = this.value;
        
        if (format === 'donor') {
            // Auto-format to +254 format for donors
            if (value && !value.startsWith('+254')) {
                if (value.startsWith('0')) {
                    value = '+254' + value.substring(1);
                } else if (value.startsWith('254')) {
                    value = '+' + value;
                } else if (/^\d/.test(value)) {
                    value = '+254' + value;
                }
            }
            // Remove non-digit characters except +
            this.value = value.replace(/[^\d+]/g, '').slice(0, 13);
        } else if (format === 'patient') {
            // Patient format: 07XXXXXXXX (10 digits starting with 0)
            if (value && !value.startsWith('0')) {
                value = '0' + value;
            }
            // Remove non-digit characters
            this.value = value.replace(/\D/g, '').slice(0, 10);
        }
        
        checkMobile();
    });
}

// ================================================
// NURSE REGISTRATION NUMBER VALIDATION
// ================================================
function initNurseRegistrationValidator(inputId, feedbackId) {
    const regInput = document.getElementById(inputId);
    const regFeedback = document.getElementById(feedbackId);
    
    if (!regInput) return;
    
    const checkRegistration = debounce(function() {
        const regNumber = regInput.value.trim();
        
        if (!regNumber) {
            regFeedback.textContent = '';
            regInput.classList.remove('is-invalid', 'is-valid');
            return;
        }
        
        // Client-side validation
        if (regNumber.length < 5 || regNumber.length > 30) {
            regFeedback.textContent = '✗ Registration number must be 5-30 characters';
            regFeedback.className = 'validation-feedback validation-error';
            regInput.classList.add('is-invalid');
            regInput.classList.remove('is-valid');
            return;
        }
        
        if (!/^[A-Z0-9]+$/.test(regNumber)) {
            regFeedback.textContent = '✗ Only uppercase letters and numbers allowed';
            regFeedback.className = 'validation-feedback validation-error';
            regInput.classList.add('is-invalid');
            regInput.classList.remove('is-valid');
            return;
        }
        
        regFeedback.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Checking...';
        regFeedback.className = 'validation-feedback validation-checking';
        
        fetch(`/ajax/check-nurse-registration/?registration_number=${encodeURIComponent(regNumber)}`)
            .then(response => response.json())
            .then(data => {
                if (data.valid) {
                    regFeedback.textContent = '✓ ' + data.message;
                    regFeedback.className = 'validation-feedback validation-success';
                    regInput.classList.remove('is-invalid');
                    regInput.classList.add('is-valid');
                } else {
                    regFeedback.textContent = '✗ ' + data.message;
                    regFeedback.className = 'validation-feedback validation-error';
                    regInput.classList.remove('is-valid');
                    regInput.classList.add('is-invalid');
                }
            })
            .catch(error => {
                console.error('Error checking registration:', error);
                regFeedback.textContent = '⚠️ Error checking registration. Please try again.';
                regFeedback.className = 'validation-feedback validation-error';
            });
    }, 500);
    
    regInput.addEventListener('input', function() {
        // Auto-uppercase
        this.value = this.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 30);
        checkRegistration();
    });
}

// ================================================
// NURSE PHONE VALIDATION
// ================================================
function initNursePhoneValidator(inputId, feedbackId) {
    const phoneInput = document.getElementById(inputId);
    const phoneFeedback = document.getElementById(feedbackId);
    
    if (!phoneInput) return;
    
    const checkPhone = debounce(function() {
        const phone = phoneInput.value.trim();
        
        if (!phone) {
            phoneFeedback.textContent = '';
            phoneInput.classList.remove('is-invalid', 'is-valid');
            return;
        }
        
        phoneFeedback.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Checking...';
        phoneFeedback.className = 'validation-feedback validation-checking';
        
        fetch(`/ajax/check-nurse-phone/?phone=${encodeURIComponent(phone)}`)
            .then(response => response.json())
            .then(data => {
                if (data.valid) {
                    phoneFeedback.textContent = '✓ ' + data.message;
                    phoneFeedback.className = 'validation-feedback validation-success';
                    phoneInput.classList.remove('is-invalid');
                    phoneInput.classList.add('is-valid');
                } else {
                    phoneFeedback.textContent = '✗ ' + data.message;
                    phoneFeedback.className = 'validation-feedback validation-error';
                    phoneInput.classList.remove('is-valid');
                    phoneInput.classList.add('is-invalid');
                }
            })
            .catch(error => {
                console.error('Error checking phone:', error);
                phoneFeedback.textContent = '⚠️ Error checking phone. Please try again.';
                phoneFeedback.className = 'validation-feedback validation-error';
            });
    }, 500);
    
    phoneInput.addEventListener('input', function() {
        let value = this.value.trim();
        
        // Auto-format to +254
        if (value && !value.startsWith('+')) {
            if (value.startsWith('0')) {
                value = '+254' + value.substring(1);
            } else if (value.startsWith('254')) {
                value = '+' + value;
            } else if (/^\d/.test(value)) {
                value = '+254' + value;
            }
        }
        
        this.value = value.replace(/[^\d+]/g, '').slice(0, 13);
        checkPhone();
    });
}

// ================================================
// INITIALIZE ALL VALIDATORS BASED ON PAGE
// ================================================
function initAllValidators() {
    // Detect which page we're on
    const isDonorPage = window.location.pathname.includes('/donor/');
    const isNursePage = window.location.pathname.includes('/nurse/');
    const isPatientPage = window.location.pathname.includes('/patient/');
    
    // Universal validators (for all)
    initUsernameValidator('id_username', 'usernameFeedback', 'usernameSuggestions');
    initEmailValidator('id_email', 'emailFeedback');
    
    // Page-specific validators
    if (isDonorPage) {
        initNationalIdValidator('id_national_id', 'nationalIdFeedback');
        initMobileValidator('id_mobile', 'mobileFeedback', 'donor');
    } else if (isNursePage) {
        initNurseRegistrationValidator('id_registration_number', 'registrationFeedback');
        initNursePhoneValidator('id_phone', 'phoneFeedback');
    } else if (isPatientPage) {
        initNationalIdValidator('id_national_id', 'nationalIdFeedback');
        initMobileValidator('id_mobile', 'mobileFeedback', 'patient');
    }
}

// Auto-initialize on DOM load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAllValidators);
} else {
    initAllValidators();
}