(() => {
    const form = document.getElementById('pricing-form');
    const results = document.getElementById('pricing-results');
    const error = document.getElementById('pricing-error');
    const shares = [...form.querySelectorAll('[name=blend_percentage]')];
    const number = new Intl.NumberFormat('pl-PL', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    let timer, controller, revision = 0;

    function balanceShares(changedIndex) {
        if (shares[changedIndex].value === '') return;
        const changed = Math.round(Math.max(0, Math.min(100, Number(shares[changedIndex].value))) * 100);
        const others = [0, 1, 2].filter(index => index !== changedIndex);
        const previous = others.map(index => Math.round(Number(shares[index].value) * 100) || 0);
        const remaining = 10000 - changed;
        const previousTotal = previous[0] + previous[1];
        const first = previousTotal ? Math.round(remaining * previous[0] / previousTotal) : Math.round(remaining / 2);
        const values = [];
        values[changedIndex] = changed;
        values[others[0]] = first;
        values[others[1]] = remaining - first;
        shares.forEach((input, index) => {
            input.value = String(values[index] / 100);
            document.getElementById(input.dataset.pair).value = input.value;
        });
    }

    function showError(message) {
        error.textContent = message;
        error.hidden = false;
        results.hidden = true;
    }

    async function calculate(currentRevision) {
        if (!form.checkValidity()) {
            showError('Sprawdź wpisane wartości.');
            results.removeAttribute('aria-busy');
            return;
        }
        controller = new AbortController();
        try {
            const response = await fetch(form.action || location.href, {
                method: 'POST', body: new FormData(form),
                headers: {'Accept': 'application/json'}, signal: controller.signal,
            });
            if (currentRevision !== revision) return;
            if (response.redirected) throw new Error('Zaloguj się ponownie.');
            const payload = await response.json();
            if (currentRevision !== revision) return;
            if (!response.ok || payload.error) {
                showError(payload.error || 'Błąd wyceny.');
                return;
            }
            const quote = payload.result;
            results.querySelectorAll('[data-result]').forEach(element => {
                const [key, metric] = element.dataset.result.split('.');
                element.textContent = number.format(quote[key][metric]);
            });
            results.querySelectorAll('[data-price-card]').forEach(element => {
                element.classList.toggle('loss', quote[element.dataset.priceCard].below_cost);
            });
            error.hidden = true;
            results.hidden = false;
        } catch (exception) {
            if (currentRevision === revision && exception.name !== 'AbortError') {
                showError(exception.message || 'Błąd połączenia.');
            }
        } finally {
            if (currentRevision === revision) results.removeAttribute('aria-busy');
        }
    }

    function schedule(delay = 180) {
        clearTimeout(timer);
        if (controller) controller.abort();
        const currentRevision = ++revision;
        results.hidden = true;
        results.setAttribute('aria-busy', 'true');
        error.hidden = true;
        timer = setTimeout(() => calculate(currentRevision), delay);
    }

    form.addEventListener('input', event => {
        const input = event.target;
        if (input.dataset.pair) {
            const paired = document.getElementById(input.dataset.pair);
            if (paired.type === 'range' && input.name === 'blend_price') {
                paired.max = Math.max(100, Number(input.value) || 0);
            }
            paired.value = input.value;
            const shareInput = input.name === 'blend_percentage' ? input : paired;
            if (shareInput.name === 'blend_percentage') {
                balanceShares(shares.indexOf(shareInput));
            }
        }
        schedule();
    });
    form.addEventListener('submit', event => {
        event.preventDefault();
        schedule(0);
    });
    form.querySelectorAll('[name=blend_price]').forEach(input => {
        const range = document.getElementById(input.dataset.pair);
        range.max = Math.max(100, Number(input.value) || 0);
        range.value = input.value;
    });
    schedule(0);
})();
