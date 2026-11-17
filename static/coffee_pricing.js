(() => {
    const form = document.getElementById('pricing-form');
    const results = document.getElementById('pricing-results');
    const error = document.getElementById('pricing-error');
    const status = document.getElementById('calculation-status');
    const totalLabel = document.getElementById('blend-total');
    const number = new Intl.NumberFormat('pl-PL', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    let timer, controller, revision = 0;

    function showError(message) {
        error.textContent = message;
        error.hidden = false;
        results.hidden = true;
        document.getElementById('discount-limit').textContent = '—';
    }

    function updateTotal() {
        const total = [...form.querySelectorAll('[name=blend_percentage]')]
            .reduce((sum, input) => sum + Number(input.value), 0);
        totalLabel.textContent = `Suma udziałów: ${number.format(total)} / 100%`;
        totalLabel.classList.toggle('expense', Math.abs(total - 100) > 0.000001);
    }

    async function calculate(currentRevision) {
        if (!form.checkValidity()) {
            status.textContent = '';
            showError('Uzupełnij prawidłowe wartości. Narzut, udziały i rabat: 0–100%; sprzedaż musi być większa od zera.');
            return;
        }
        controller = new AbortController();
        try {
            const response = await fetch(form.action || location.href, {
                method: 'POST', body: new FormData(form),
                headers: {'Accept': 'application/json'}, signal: controller.signal,
            });
            if (currentRevision !== revision) return;
            if (response.redirected) throw new Error('Sesja wygasła. Zaloguj się ponownie, aby przeliczyć cenę.');
            const payload = await response.json();
            if (currentRevision !== revision) return;
            if (!response.ok || payload.error) {
                showError(payload.error || 'Nie udało się przeliczyć ceny.');
                return;
            }
            const quote = payload.result;
            results.querySelectorAll('[data-result]').forEach(element => {
                const [key, metric] = element.dataset.result.split('.');
                const value = quote[key][metric];
                element.textContent = value === null ? '—' : number.format(value);
            });
            results.querySelectorAll('[data-summary]').forEach(element => {
                element.textContent = number.format(quote[element.dataset.summary]);
            });
            results.querySelectorAll('[data-breakeven]').forEach(element => {
                const value = quote[element.dataset.breakeven].break_even_kg;
                element.textContent = value === null ? 'Brak — cena nie pokrywa kosztów zmiennych' : `${number.format(value)} kg/mies.`;
            });
            results.querySelectorAll('[data-profit]').forEach(element => {
                element.classList.toggle('expense', quote[element.dataset.profit].below_cost);
                element.classList.toggle('income', !quote[element.dataset.profit].below_cost);
            });
            for (const channel of ['b2c', 'b2b']) {
                const loss = quote[`${channel}_250`].below_cost || quote[`${channel}_1000`].below_cost;
                document.getElementById(`${channel}-warning`).hidden = !loss;
                document.getElementById(`${channel}-card`).classList.toggle('loss', loss);
            }
            document.getElementById('discount-limit').textContent = `${number.format(quote.max_discount_pct)}%`;
            error.hidden = true;
            results.hidden = false;
            status.textContent = 'Wycena aktualna';
        } catch (exception) {
            if (currentRevision === revision && exception.name !== 'AbortError') {
                showError(exception.message || 'Błąd połączenia. Spróbuj ponownie.');
            }
        } finally {
            if (currentRevision === revision) {
                results.classList.remove('pending');
                results.removeAttribute('aria-busy');
                if (results.hidden) status.textContent = '';
            }
        }
    }

    function schedule(delay = 180) {
        clearTimeout(timer);
        if (controller) controller.abort();
        const currentRevision = ++revision;
        updateTotal();
        // Never leave stale prices or a previous discount limit visible.
        results.hidden = true;
        document.getElementById('discount-limit').textContent = '—';
        error.hidden = true;
        status.textContent = 'Przeliczanie…';
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
