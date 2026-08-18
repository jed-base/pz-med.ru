(() => {
  'use strict';

  const STORAGE_KEY = 'pzmed_demo_state_v1';
  const RESET_MS = 60 * 60 * 1000;
  const CURRENT_USER_ID = 1;

  const divisions = [
    'Поликлиническое подразделение №1',
    'Поликлиническое подразделение №2',
    'Диагностическое подразделение'
  ];

  const departments = [
    { name: 'Терапевтическое отделение №1', division: divisions[0] },
    { name: 'Терапевтическое отделение №2', division: divisions[0] },
    { name: 'Хирургическое отделение', division: divisions[0] },
    { name: 'Отделение медицинской профилактики', division: divisions[1] },
    { name: 'Женская консультация', division: divisions[1] },
    { name: 'Отделение функциональной диагностики', division: divisions[2] },
    { name: 'Отделение лучевой диагностики', division: divisions[2] }
  ];

  const employeeSeed = [
    ['Иванов Иван Иванович', 'Заведующий терапевтическим отделением', 0],
    ['Петрова Анна Алексеевна', 'Врач-терапевт участковый', 0],
    ['Сидоров Николай Николаевич', 'Врач-терапевт участковый', 0],
    ['Кузнецова Мария Сергеевна', 'Врач-терапевт участковый', 0],
    ['Смирнова Елена Викторовна', 'Медицинская сестра участковая', 0],
    ['Васильев Андрей Павлович', 'Врач-терапевт участковый', 0],
    ['Попова Ольга Дмитриевна', 'Старшая медицинская сестра', 0],
    ['Михайлов Сергей Александрович', 'Медицинский брат участковый', 0],

    ['Новикова Ирина Михайловна', 'Заведующий терапевтическим отделением', 1],
    ['Федоров Алексей Олегович', 'Врач-терапевт участковый', 1],
    ['Морозова Наталья Игоревна', 'Врач-терапевт участковый', 1],
    ['Волков Дмитрий Сергеевич', 'Врач-терапевт участковый', 1],
    ['Алексеева Татьяна Романовна', 'Медицинская сестра участковая', 1],
    ['Лебедева Екатерина Андреевна', 'Медицинская сестра участковая', 1],

    ['Семенов Роман Ильич', 'Заведующий хирургическим отделением', 2],
    ['Егорова Полина Максимовна', 'Врач-хирург', 2],
    ['Павлов Артем Денисович', 'Врач-хирург', 2],
    ['Козлова Юлия Владимировна', 'Медицинская сестра', 2],
    ['Степанов Максим Андреевич', 'Врач-травматолог-ортопед', 2],
    ['Николаева Светлана Евгеньевна', 'Старшая медицинская сестра', 2],

    ['Орлов Павел Михайлович', 'Заведующий отделением', 3],
    ['Андреева Виктория Ильинична', 'Врач по медицинской профилактике', 3],
    ['Макаров Евгений Олегович', 'Врач по медицинской профилактике', 3],
    ['Захарова Дарья Романовна', 'Медицинская сестра', 3],
    ['Зайцев Антон Сергеевич', 'Фельдшер', 3],

    ['Соловьева Марина Павловна', 'Заведующая женской консультацией', 4],
    ['Борисова Кирилла Александровна', 'Врач-акушер-гинеколог', 4],
    ['Яковлева Алина Игоревна', 'Врач-акушер-гинеколог', 4],
    ['Григорьева Ирина Денисовна', 'Акушерка', 4],
    ['Романова Ксения Андреевна', 'Акушерка', 4],

    ['Воробьев Олег Николаевич', 'Заведующий отделением', 5],
    ['Сергеева Надежда Петровна', 'Врач функциональной диагностики', 5],
    ['Ковалев Владислав Игоревич', 'Врач функциональной диагностики', 5],
    ['Белова Анастасия Сергеевна', 'Медицинская сестра', 5],
    ['Комаров Денис Викторович', 'Медицинский брат', 5],

    ['Тарасова Любовь Андреевна', 'Заведующая отделением', 6],
    ['Белов Михаил Юрьевич', 'Врач-рентгенолог', 6],
    ['Гусева Вера Александровна', 'Врач ультразвуковой диагностики', 6],
    ['Киселев Артур Романович', 'Рентгенолаборант', 6],
    ['Миронова Инна Олеговна', 'Рентгенолаборант', 6]
  ];

  const firstVacationOffsets = [
    28, 42, 63, -3, 82, 14, 55, 71, 34, 48,
    66, 91, 106, 22, 39, 57, 74, 96, 118, 131,
    12, 29, 47, 68, 89, 104, 121, 138, 154, 171,
    18, 36, 59, 77, 99, 116, 133, 151, 169, 187
  ];

  const today = startOfDay(new Date());
  const dateKey = toISO(today);

  const employees = employeeSeed.map((row, index) => {
    const id = index + 1;
    const department = departments[row[2]];
    const specificBirthdayOffsets = { 2: 7, 4: 18, 7: 31, 10: 12, 16: 26, 22: 5, 32: 15, 38: 22 };
    const birthdayOffset = specificBirthdayOffsets[id] ?? ((id * 23 + 11) % 330) + 10;
    const nextBirthday = addDays(today, birthdayOffset);
    const birthYear = 1969 + ((id * 3) % 29);
    const birthDate = new Date(birthYear, nextBirthday.getMonth(), nextBirthday.getDate());
    return {
      id,
      name: row[0],
      shortName: initials(row[0]),
      position: row[1],
      department: department.name,
      division: department.division,
      birthdayOffset,
      birthDate,
      nextBirthday,
      email: `demo${String(id).padStart(2, '0')}@pz-med.local`,
      cabinet: 200 + ((id * 7) % 80)
    };
  });

  const vacations = employees.flatMap((employee, index) => {
    const first = firstVacationOffsets[index];
    return [first, first + 120, first + 240].map((offset, periodIndex) => {
      const start = addDays(today, offset);
      const end = addDays(start, 13); // ровно 14 календарных дней включительно
      return {
        id: `${employee.id}-${periodIndex + 1}`,
        employeeId: employee.id,
        period: periodIndex + 1,
        start,
        end,
        days: 14,
        status: offset < -13 ? 'Завершён' : offset <= 0 ? 'Идёт сейчас' : 'Запланирован'
      };
    });
  });

  const absences = [
    absence(4, 'Отпуск', -3, 10, 'Ежегодный оплачиваемый отпуск'),
    absence(3, 'Больничный', -2, 5, 'Временная нетрудоспособность'),
    absence(7, 'Обучение', 0, 1, 'Повышение квалификации'),
    absence(18, 'Отпуск', 0, 13, 'Ежегодный оплачиваемый отпуск'),
    absence(33, 'Командировка', -1, 2, 'Выездное обучение')
  ];

  const announcements = [
    { id: 1, title: 'Совещание заведующих отделениями', text: 'В четверг в 14:30 — организационное совещание в конференц-зале. Просьба подготовить краткую информацию по текущим задачам.', author: 'Администрация', created: addDays(today, -1) },
    { id: 2, title: 'Обновлены внутренние алгоритмы', text: 'В разделе «Алгоритмы» опубликована новая версия порядка маршрутизации пациентов на диагностические исследования.', author: 'Организационно-методический отдел', created: addDays(today, -3) },
    { id: 3, title: 'График дежурств на следующий месяц', text: 'Открыта запись на дежурства. Руководителям отделений необходимо проверить заполнение свободных дат.', author: 'Администрация', created: addDays(today, -5) }
  ];

  const duties = buildDuties();
  const algorithms = [
    ['Действия при неотложном состоянии в кабинете', 'Для врачей и среднего медперсонала', 'Обновлён 2 дня назад'],
    ['Маршрутизация на КТ и МРТ', 'Терапевтические и хирургическое отделения', 'Актуальная версия'],
    ['Порядок передачи дежурства', 'Все подразделения', 'Обновлён неделю назад'],
    ['Алгоритм работы с результатами критических исследований', 'Врачи', 'Актуальная версия'],
    ['Порядок действий при конфликтной ситуации', 'Все сотрудники', 'Актуальная версия']
  ];

  const documents = [
    ['Служебная записка', 'Автоматическая подстановка адресата, автора и подразделения'],
    ['Заявление на предоставление отпуска', 'Данные сотрудника и периоды отпуска'],
    ['Сводный отчёт по вакантным ставкам', 'Формирование по данным подразделения'],
    ['Направление на обучение', 'Сотрудник, должность, сроки и основание'],
    ['Акт', 'Шаблон с реквизитами организации']
  ];

  const baseTasks = [
    makeTask(101, 'Проверить сведения по отчёту за неделю', 1, 2, 0, 'В работе'),
    makeTask(102, 'Согласовать график дежурств отделения', 1, 7, 1, 'Новая'),
    makeTask(103, 'Подготовить информацию к совещанию заведующих', 1, 1, 2, 'В работе'),
    makeTask(104, 'Проверить актуальность локального алгоритма', 9, 1, 5, 'Новая'),
    makeTask(105, 'Уточнить список сотрудников на обучение', 1, 5, 7, 'Новая'),
    makeTask(106, 'Заполнить сведения по табличному отчёту', 1, 2, -1, 'Просрочена')
  ];

  const reports = [
    { id: 1, name: 'Еженедельный мониторинг нагрузки', period: 'Текущая неделя', due: addDays(today, 2), status: 'Ожидает заполнения', scope: 'Терапевтическое отделение №1' },
    { id: 2, name: 'Сведения о работе на вакантных ставках', period: monthName(today), due: addDays(today, 6), status: 'Черновик', scope: 'Терапевтическое отделение №1' },
    { id: 3, name: 'Потребность в расходных материалах', period: 'Следующий месяц', due: addDays(today, 9), status: 'Новая форма', scope: 'Поликлиническое подразделение №1' },
    { id: 4, name: 'Контроль выполнения профилактических мероприятий', period: 'Текущий месяц', due: addDays(today, 13), status: 'Открыт', scope: 'Учреждение' }
  ];

  const baseDeferred = [
    { id: 1, patient: 'Демо-пациент №1042', service: 'Эхокардиография', priority: 'Обычная', desired: addDays(today, 5), status: 'Ожидание' },
    { id: 2, patient: 'Демо-пациент №1158', service: 'Консультация кардиолога', priority: 'Повышенная', desired: addDays(today, 2), status: 'Ожидание' },
    { id: 3, patient: 'Демо-пациент №1214', service: 'УЗИ сосудов нижних конечностей', priority: 'Обычная', desired: addDays(today, 8), status: 'Предложен слот' },
    { id: 4, patient: 'Демо-пациент №1320', service: 'Дневной стационар', priority: 'Обычная', desired: addDays(today, 12), status: 'Ожидание' },
    { id: 5, patient: 'Демо-пациент №1351', service: 'Холтеровское мониторирование', priority: 'Повышенная', desired: addDays(today, 4), status: 'Ожидание' },
    { id: 6, patient: 'Демо-пациент №1408', service: 'Консультация невролога', priority: 'Обычная', desired: addDays(today, 16), status: 'Записан' }
  ];

  const baseMessages = {
    1: [
      { from: 2, text: 'Иван Иванович, отчёт за участок заполнила. Можно проверять.', offsetMinutes: -70 },
      { from: 1, text: 'Спасибо, посмотрю сегодня.', offsetMinutes: -63 }
    ],
    2: [
      { from: 7, text: 'На субботнее дежурство пока записались трое. Нужен ещё один человек.', offsetMinutes: -180 },
      { from: 1, text: 'Хорошо, напомню коллегам.', offsetMinutes: -171 }
    ],
    3: [
      { from: 9, text: 'Коллеги, новую форму отчёта открыли до конца недели.', offsetMinutes: -1450 },
      { from: 10, text: 'Увидел, спасибо.', offsetMinutes: -1430 }
    ]
  };

  const chats = [
    { id: 1, name: 'Петрова А.А.', subtitle: 'Терапевтическое отделение №1' },
    { id: 2, name: 'Дежурства — терапия', subtitle: 'Групповой чат' },
    { id: 3, name: 'Заведующие отделениями', subtitle: 'Групповой чат' }
  ];

  let state = loadState();
  let currentView = (location.hash || '#dashboard').replace('#', '') || 'dashboard';
  let currentChat = 1;

  const content = document.getElementById('app-content');
  const pageTitle = document.getElementById('page-title');
  const toast = document.getElementById('toast');
  const taskDialog = document.getElementById('task-dialog');
  const taskForm = document.getElementById('task-form');
  const taskAssignee = document.getElementById('task-assignee');
  const taskTitle = document.getElementById('task-title');
  const taskDue = document.getElementById('task-due');

  init();

  function init() {
    document.getElementById('today-chip').textContent = formatLong(today);
    taskAssignee.innerHTML = employees
      .filter(e => e.department === employees[0].department)
      .map(e => `<option value="${e.id}">${escapeHtml(e.shortName)} — ${escapeHtml(e.position)}</option>`)
      .join('');
    taskDue.value = toISO(addDays(today, 3));

    document.querySelectorAll('[data-view]').forEach(el => {
      el.addEventListener('click', event => {
        const view = event.currentTarget.dataset.view;
        if (!view) return;
        event.preventDefault();
        navigate(view);
      });
    });

    document.querySelector('.mobile-menu').addEventListener('click', () => document.body.classList.toggle('menu-open'));

    taskForm.addEventListener('submit', event => {
      const submitter = event.submitter;
      if (!submitter || submitter.value === 'cancel') return;
      event.preventDefault();
      createTaskFromDialog();
    });

    renderView(currentView);
  }

  function navigate(view) {
    currentView = view;
    location.hash = view;
    document.body.classList.remove('menu-open');
    document.querySelectorAll('.nav-item').forEach(el => el.classList.toggle('active', el.dataset.view === view));
    renderView(view);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function renderView(view) {
    const views = {
      dashboard: ['Рабочая панель', renderDashboard],
      tasks: ['Задачи', renderTasks],
      reports: ['Отчёты', renderReports],
      employees: ['Сотрудники', renderEmployees],
      vacations: ['Отпуска', renderVacations],
      absences: ['Отсутствия', renderAbsences],
      duties: ['Дежурства', renderDuties],
      algorithms: ['Алгоритмы', renderAlgorithms],
      documents: ['Документы', renderDocuments],
      deferred: ['Отложенная запись', renderDeferred],
      messages: ['Сообщения', renderMessages],
      structure: ['Структура учреждения', renderStructure]
    };
    const selected = views[view] || views.dashboard;
    pageTitle.textContent = selected[0];
    selected[1]();
  }

  function renderDashboard() {
    const currentUser = employee(CURRENT_USER_ID);
    const departmentEmployees = employees.filter(e => e.department === currentUser.department);
    const birthdays = departmentEmployees
      .filter(e => e.id !== CURRENT_USER_ID && e.birthdayOffset >= 0)
      .sort((a, b) => a.birthdayOffset - b.birthdayOffset)
      .slice(0, 2);
    const todayAbsences = absences.filter(a => a.start <= today && a.end >= today);
    const pendingTasks = state.tasks.filter(t => t.authorId === CURRENT_USER_ID || t.assigneeId === CURRENT_USER_ID).filter(t => t.status !== 'Выполнена');
    const nextDuties = duties.slice(0, 2);
    const activeAnnouncements = announcements.filter(a => !state.dismissedAnnouncements.includes(a.id));

    content.innerHTML = `
      <div class="page-intro">
        <div>
          <h2>Добрый день, Иван Иванович</h2>
          <p>Демонстрационная рабочая панель заведующего отделением. Даты и события автоматически рассчитываются относительно дня просмотра.</p>
        </div>
        <div class="page-actions"><button class="btn btn-primary" onclick="Demo.openTaskDialog()">+ Новая задача</button></div>
      </div>

      <div class="dashboard-grid">
        ${metric('Сотрудники отделения', departmentEmployees.length, 'включая заведующего', 'span-3')}
        ${metric('Требуют действия', pendingTasks.length, 'задачи и отчёты', 'span-3')}
        ${metric('Отсутствуют сегодня', todayAbsences.length, 'в демонстрационной организации', 'span-3')}
        ${metric('Ближайшее дежурство', formatShort(nextDuties[0].date), weekday(nextDuties[0].date), 'span-3')}

        <section class="card card-pad span-7">
          <div class="card-title-row"><h3>Требуют действия</h3><button class="card-link" onclick="Demo.go('tasks')">Все задачи →</button></div>
          <div class="action-list">
            ${pendingTasks.slice(0, 5).map(task => actionTask(task)).join('')}
            ${reports.slice(0, 2).map(r => `
              <div class="action-item">
                <span class="item-icon">▤</span>
                <div class="item-copy"><b>${escapeHtml(r.name)}</b><small>${escapeHtml(r.period)} · срок ${formatDate(r.due)}</small></div>
                <span class="status status-blue">Отчёт</span>
              </div>`).join('')}
          </div>
        </section>

        <section class="card card-pad span-5">
          <div class="card-title-row"><h3>Ближайшие дни рождения</h3><small>${escapeHtml(currentUser.department)}</small></div>
          <div class="compact-list">
            ${birthdays.map(e => `
              <div class="compact-item">
                <span class="person-avatar">${escapeHtml(initialLetters(e.name))}</span>
                <div class="item-copy"><b>${escapeHtml(e.shortName)}</b><small>${escapeHtml(e.position)}</small></div>
                <div class="item-meta"><b>${formatDate(e.nextBirthday)}</b><br>${relativeDays(e.birthdayOffset)}</div>
              </div>`).join('')}
          </div>
          <div style="margin-top:10px;color:#71817a;font-size:.65rem">У Петровой А.А. день рождения всегда показывается через 7 дней от даты запуска демо.</div>
        </section>

        <section class="card card-pad span-6">
          <div class="card-title-row"><h3>Отсутствуют сегодня</h3><button class="card-link" onclick="Demo.go('absences')">Открыть журнал →</button></div>
          <div class="compact-list">
            ${todayAbsences.map(a => {
              const e = employee(a.employeeId);
              return `<div class="compact-item"><span class="person-avatar">${escapeHtml(initialLetters(e.name))}</span><div class="item-copy"><b>${escapeHtml(e.shortName)}</b><small>${escapeHtml(e.department)}</small></div><span class="status ${absenceStatusClass(a.type)}">${escapeHtml(a.type)}</span></div>`;
            }).join('')}
          </div>
        </section>

        <section class="card card-pad span-6">
          <div class="card-title-row"><h3>Ближайшие дежурства</h3><button class="card-link" onclick="Demo.go('duties')">График →</button></div>
          <div class="compact-list">
            ${nextDuties.map(d => `<div class="compact-item"><span class="item-icon">◷</span><div class="item-copy"><b>${formatLong(d.date)}</b><small>${escapeHtml(d.type)} · ${d.participants.length} участника</small></div><span class="status status-green">${d.open ? 'Запись открыта' : 'Закрыто'}</span></div>`).join('')}
          </div>
        </section>

        <section class="card card-pad span-12">
          <div class="card-title-row"><h3>Объявления</h3><small>Внутренняя лента учреждения</small></div>
          ${activeAnnouncements.length ? activeAnnouncements.map(a => `
            <article class="announcement">
              <button class="dismiss-announcement" onclick="Demo.dismissAnnouncement(${a.id})" title="Скрыть">×</button>
              <b>${escapeHtml(a.title)}</b>
              <p>${escapeHtml(a.text)}</p>
              <small>${escapeHtml(a.author)} · ${formatDate(a.created)}</small>
            </article>`).join('') : `<div class="empty-state"><b>Все объявления скрыты</b><span>Они вернутся после автоматического сброса демо.</span></div>`}
        </section>
      </div>`;
  }

  function renderTasks(query = '') {
    const normalized = query.trim().toLowerCase();
    const list = state.tasks.filter(task => {
      const assignee = employee(task.assigneeId);
      return !normalized || `${task.title} ${assignee.name} ${task.status}`.toLowerCase().includes(normalized);
    });

    content.innerHTML = `
      <div class="page-intro">
        <div><h2>Задачи</h2><p>Поручения со сроками, исполнителями и независимыми статусами. В демо можно создать задачу и отметить её выполненной.</p></div>
        <div class="page-actions"><button class="btn btn-primary" onclick="Demo.openTaskDialog()">+ Новая задача</button></div>
      </div>
      <div class="search-row">
        <input class="search-input" id="task-search" placeholder="Поиск по задачам или исполнителю" value="${escapeAttr(query)}">
        <button class="btn btn-secondary" onclick="Demo.resetSandbox()">Сбросить демо</button>
      </div>
      <div class="table-wrap"><table class="demo-table">
        <thead><tr><th>Задача</th><th>Исполнитель</th><th>Срок</th><th>Статус</th><th></th></tr></thead>
        <tbody>${list.map(taskRow).join('')}</tbody>
      </table></div>`;

    document.getElementById('task-search').addEventListener('input', e => renderTasks(e.target.value));
  }

  function renderReports() {
    content.innerHTML = `
      <div class="page-intro"><div><h2>Табличные отчёты</h2><p>Пример форм, которые руководитель видит в своём контуре. Здесь показаны разные уровни и статусы.</p></div></div>
      <div class="table-wrap"><table class="demo-table">
        <thead><tr><th>Форма</th><th>Период</th><th>Уровень</th><th>Срок</th><th>Статус</th><th></th></tr></thead>
        <tbody>${reports.map(r => `<tr><td><b>${escapeHtml(r.name)}</b></td><td>${escapeHtml(r.period)}</td><td>${escapeHtml(r.scope)}</td><td>${formatDate(r.due)}</td><td><span class="status ${reportStatusClass(r.status)}">${escapeHtml(r.status)}</span></td><td><button class="btn btn-sm" onclick="Demo.fakeOpen('Открыта демонстрационная форма отчёта «${escapeJs(r.name)}»')">Открыть</button></td></tr>`).join('')}</tbody>
      </table></div>`;
  }

  function renderEmployees(query = '', departmentFilter = '') {
    const normalized = query.trim().toLowerCase();
    const list = employees.filter(e => {
      const matchesQuery = !normalized || `${e.name} ${e.position} ${e.department} ${e.division}`.toLowerCase().includes(normalized);
      const matchesDepartment = !departmentFilter || e.department === departmentFilter;
      return matchesQuery && matchesDepartment;
    });
    content.innerHTML = `
      <div class="page-intro"><div><h2>Сотрудники</h2><p>В демонстрационной организации создано 40 вымышленных сотрудников в трёх подразделениях и семи отделениях.</p></div></div>
      <div class="search-row">
        <input class="search-input" id="employee-search" placeholder="ФИО, должность, отделение" value="${escapeAttr(query)}">
        <select class="select-input" id="employee-department"><option value="">Все отделения</option>${departments.map(d => `<option ${d.name === departmentFilter ? 'selected' : ''}>${escapeHtml(d.name)}</option>`).join('')}</select>
      </div>
      <div class="table-wrap"><table class="demo-table"><thead><tr><th>Сотрудник</th><th>Подразделение</th><th>Отделение</th><th>Кабинет</th><th>Ближайший ДР</th></tr></thead><tbody>
        ${list.map(e => `<tr><td><div class="person-cell"><span class="person-avatar">${escapeHtml(initialLetters(e.name))}</span><div><b>${escapeHtml(e.shortName)}</b><small>${escapeHtml(e.position)}</small></div></div></td><td>${escapeHtml(e.division)}</td><td>${escapeHtml(e.department)}</td><td>${e.cabinet}</td><td>${formatDate(e.nextBirthday)}</td></tr>`).join('')}
      </tbody></table></div>`;
    document.getElementById('employee-search').addEventListener('input', e => renderEmployees(e.target.value, document.getElementById('employee-department').value));
    document.getElementById('employee-department').addEventListener('change', e => renderEmployees(document.getElementById('employee-search').value, e.target.value));
  }

  function renderVacations(query = '') {
    const normalized = query.trim().toLowerCase();
    const rows = employees.filter(e => !normalized || `${e.name} ${e.department}`.toLowerCase().includes(normalized));
    content.innerHTML = `
      <div class="page-intro"><div><h2>Отпуска</h2><p>У каждого из 40 демонстрационных сотрудников сформировано ровно три периода ежегодного отпуска по 14 календарных дней.</p></div></div>
      <div class="search-row"><input class="search-input" id="vacation-search" placeholder="Найти сотрудника или отделение" value="${escapeAttr(query)}"><span class="status status-green">40 сотрудников · 120 периодов</span></div>
      <div class="table-wrap"><table class="demo-table"><thead><tr><th>Сотрудник</th><th>Отделение</th><th>Период 1</th><th>Период 2</th><th>Период 3</th></tr></thead><tbody>
        ${rows.map(e => {
          const periods = vacations.filter(v => v.employeeId === e.id);
          return `<tr><td><div class="person-cell"><span class="person-avatar">${escapeHtml(initialLetters(e.name))}</span><div><b>${escapeHtml(e.shortName)}</b><small>${escapeHtml(e.position)}</small></div></div></td><td>${escapeHtml(e.department)}</td>${periods.map(v => `<td><span class="period-chip">${formatRange(v.start, v.end)} · 14 дней</span></td>`).join('')}</tr>`;
        }).join('')}
      </tbody></table></div>`;
    document.getElementById('vacation-search').addEventListener('input', e => renderVacations(e.target.value));
  }

  function renderAbsences() {
    content.innerHTML = `
      <div class="page-intro"><div><h2>Отсутствия сотрудников</h2><p>Актуальные отсутствия рассчитываются относительно сегодняшней даты, чтобы карточки рабочей панели всегда выглядели живыми.</p></div></div>
      <div class="table-wrap"><table class="demo-table"><thead><tr><th>Сотрудник</th><th>Причина</th><th>Период</th><th>Комментарий</th><th>Состояние</th></tr></thead><tbody>
        ${absences.map(a => {
          const e = employee(a.employeeId);
          const isToday = a.start <= today && a.end >= today;
          return `<tr><td><div class="person-cell"><span class="person-avatar">${escapeHtml(initialLetters(e.name))}</span><div><b>${escapeHtml(e.shortName)}</b><small>${escapeHtml(e.department)}</small></div></div></td><td>${escapeHtml(a.type)}</td><td>${formatRange(a.start, a.end)}</td><td>${escapeHtml(a.comment)}</td><td><span class="status ${isToday ? 'status-red' : 'status-gray'}">${isToday ? 'Отсутствует сегодня' : 'Запланировано'}</span></td></tr>`;
        }).join('')}
      </tbody></table></div>`;
  }

  function renderDuties() {
    content.innerHTML = `
      <div class="page-intro"><div><h2>Дежурства</h2><p>Ближайшие даты автоматически привязаны к текущим выходным. На первую дату можно записать Иванова И.И. и сразу увидеть изменение.</p></div></div>
      <div class="module-grid">
        ${duties.map(d => {
          const joined = state.dutyJoined.includes(d.id);
          const participants = joined && !d.participants.includes(CURRENT_USER_ID) ? [...d.participants, CURRENT_USER_ID] : d.participants;
          return `<article class="card duty-card"><div class="duty-date">${formatLong(d.date)}</div><h3>${escapeHtml(d.type)}</h3><p>${escapeHtml(d.scope)}</p><div class="duty-people">${participants.map(id => `<span class="person-pill">${escapeHtml(employee(id).shortName)}</span>`).join('')}</div><button class="btn ${joined ? 'btn-secondary' : 'btn-primary'}" onclick="Demo.toggleDuty(${d.id})">${joined ? 'Отменить мою запись' : 'Записаться на дежурство'}</button></article>`;
        }).join('')}
      </div>`;
  }

  function renderAlgorithms() {
    content.innerHTML = `
      <div class="page-intro"><div><h2>Алгоритмы и инструкции</h2><p>Локальные рабочие алгоритмы можно адресовать нужным подразделениям, отделениям и должностям.</p></div></div>
      <div class="module-grid">${algorithms.map((a, i) => `<article class="card module-card"><span class="status ${i < 2 ? 'status-green' : 'status-gray'}">${i < 2 ? 'Рекомендуется' : 'Доступен'}</span><h3 style="margin-top:12px">${escapeHtml(a[0])}</h3><p>${escapeHtml(a[1])}</p><div class="module-footer"><small style="color:#71817a">${escapeHtml(a[2])}</small><button class="btn btn-sm" onclick="Demo.fakeOpen('Открыт демонстрационный алгоритм «${escapeJs(a[0])}»')">Открыть</button></div></article>`).join('')}</div>`;
  }

  function renderDocuments() {
    content.innerHTML = `
      <div class="page-intro"><div><h2>Документы</h2><p>Пример библиотеки шаблонов. Кнопка «Сформировать» имитирует создание документа и показывает поведение интерфейса.</p></div></div>
      <div class="module-grid">${documents.map(d => `<article class="card module-card"><span class="item-icon">▱</span><h3 style="margin-top:12px">${escapeHtml(d[0])}</h3><p>${escapeHtml(d[1])}</p><div class="module-footer"><span class="status status-green">Шаблон готов</span><button class="btn btn-sm btn-primary" onclick="Demo.generateDocument('${escapeJs(d[0])}')">Сформировать</button></div></article>`).join('')}</div>`;
  }

  function renderDeferred() {
    content.innerHTML = `
      <div class="page-intro"><div><h2>Отложенная запись</h2><p>Демонстрационный журнал ожидания дефицитных консультаций и исследований.</p></div><div class="page-actions"><button class="btn btn-primary" onclick="Demo.addDeferred()">+ Добавить запись</button></div></div>
      <div class="table-wrap"><table class="demo-table"><thead><tr><th>Пациент</th><th>Услуга</th><th>Приоритет</th><th>Желаемый срок</th><th>Статус</th><th></th></tr></thead><tbody>
        ${state.deferred.map(r => `<tr><td>${escapeHtml(r.patient)}</td><td><b>${escapeHtml(r.service)}</b></td><td><span class="status ${r.priority === 'Повышенная' ? 'status-amber' : 'status-gray'}">${escapeHtml(r.priority)}</span></td><td>${formatDate(new Date(r.desired))}</td><td><span class="status ${deferredStatusClass(r.status)}">${escapeHtml(r.status)}</span></td><td><button class="btn btn-sm" onclick="Demo.advanceDeferred(${r.id})">Следующий статус</button></td></tr>`).join('')}
      </tbody></table></div>`;
  }

  function renderMessages() {
    const active = chats.find(c => c.id === currentChat) || chats[0];
    const messages = state.messages[currentChat] || [];
    content.innerHTML = `
      <div class="page-intro"><div><h2>Внутренние сообщения</h2><p>Рабочая переписка внутри демонстрационной организации. Можно отправить сообщение — оно сохранится до сброса песочницы.</p></div></div>
      <div class="message-layout">
        <aside class="chat-list"><div class="chat-list-head"><b>Чаты</b></div>${chats.map(c => `<button class="chat-row ${c.id === currentChat ? 'active' : ''}" onclick="Demo.openChat(${c.id})"><span class="person-avatar">${c.id === 1 ? 'ПА' : 'ГР'}</span><span class="chat-row-copy"><b>${escapeHtml(c.name)}</b><small>${escapeHtml(lastMessage(c.id))}</small></span></button>`).join('')}</aside>
        <section class="chat-panel"><div class="chat-head"><b>${escapeHtml(active.name)}</b></div><div class="chat-messages" id="chat-messages">${messages.map(messageBubble).join('')}</div><div class="chat-compose"><input class="text-input" id="chat-input" placeholder="Напишите сообщение"><button class="btn btn-primary" onclick="Demo.sendMessage()">Отправить</button></div></section>
      </div>`;
    const input = document.getElementById('chat-input');
    input.addEventListener('keydown', e => { if (e.key === 'Enter') Demo.sendMessage(); });
    requestAnimationFrame(() => { const box = document.getElementById('chat-messages'); if (box) box.scrollTop = box.scrollHeight; });
  }

  function renderStructure() {
    content.innerHTML = `
      <div class="page-intro"><div><h2>Структура учреждения</h2><p>Демонстрационная организация специально заполнена несколькими уровнями, чтобы показать работу ролевой модели.</p></div></div>
      <div class="structure-grid">
        ${divisions.map(div => {
          const depList = departments.filter(d => d.division === div);
          const count = employees.filter(e => e.division === div).length;
          return `<article class="card structure-card"><span class="status status-green">${count} сотрудников</span><h3 style="margin-top:12px">${escapeHtml(div)}</h3><ul>${depList.map(d => `<li><b>${escapeHtml(d.name)}</b><br><span style="color:#84918c">${employees.filter(e => e.department === d.name).length} сотрудников</span></li>`).join('')}</ul></article>`;
        }).join('')}
      </div>`;
  }

  function openTaskDialog() {
    taskTitle.value = '';
    taskAssignee.value = '2';
    taskDue.value = toISO(addDays(today, 3));
    if (typeof taskDialog.showModal === 'function') taskDialog.showModal();
  }

  function createTaskFromDialog() {
    const title = taskTitle.value.trim();
    if (!title) return;
    const newTask = {
      id: Date.now(),
      title,
      authorId: CURRENT_USER_ID,
      assigneeId: Number(taskAssignee.value),
      due: taskDue.value,
      status: 'Новая',
      created: toISO(today)
    };
    state.tasks.unshift(newTask);
    saveState();
    taskDialog.close();
    showToast('Задача создана в демонстрационной версии');
    if (currentView === 'tasks') renderTasks(); else renderDashboard();
  }

  function toggleTask(id) {
    const task = state.tasks.find(t => Number(t.id) === Number(id));
    if (!task) return;
    task.status = task.status === 'Выполнена' ? 'В работе' : 'Выполнена';
    saveState();
    showToast(task.status === 'Выполнена' ? 'Задача отмечена выполненной' : 'Задача возвращена в работу');
    renderTasks();
  }

  function toggleDuty(id) {
    const index = state.dutyJoined.indexOf(id);
    if (index >= 0) {
      state.dutyJoined.splice(index, 1);
      showToast('Запись на дежурство отменена');
    } else {
      state.dutyJoined.push(id);
      showToast('Иванов И.И. записан на дежурство');
    }
    saveState();
    renderDuties();
  }

  function dismissAnnouncement(id) {
    if (!state.dismissedAnnouncements.includes(id)) state.dismissedAnnouncements.push(id);
    saveState();
    renderDashboard();
  }

  function addDeferred() {
    const id = Math.max(...state.deferred.map(r => r.id), 0) + 1;
    state.deferred.unshift({
      id,
      patient: `Демо-пациент №${1500 + id * 7}`,
      service: 'Консультация эндокринолога',
      priority: 'Обычная',
      desired: toISO(addDays(today, 10)),
      status: 'Ожидание'
    });
    saveState();
    showToast('Запись добавлена в журнал');
    renderDeferred();
  }

  function advanceDeferred(id) {
    const record = state.deferred.find(r => r.id === id);
    if (!record) return;
    const flow = ['Ожидание', 'Предложен слот', 'Записан'];
    const index = flow.indexOf(record.status);
    record.status = flow[(index + 1) % flow.length];
    saveState();
    showToast(`Статус: ${record.status}`);
    renderDeferred();
  }

  function openChat(id) {
    currentChat = id;
    renderMessages();
  }

  function sendMessage() {
    const input = document.getElementById('chat-input');
    if (!input) return;
    const text = input.value.trim();
    if (!text) return;
    if (!state.messages[currentChat]) state.messages[currentChat] = [];
    state.messages[currentChat].push({ from: CURRENT_USER_ID, text, createdAt: new Date().toISOString() });
    saveState();
    renderMessages();
  }

  function resetSandbox() {
    localStorage.removeItem(STORAGE_KEY);
    state = freshState();
    saveState();
    showToast('Демонстрационные изменения сброшены');
    renderView(currentView);
  }

  function generateDocument(name) {
    showToast(`«${name}»: демонстрационный документ сформирован`);
  }

  function fakeOpen(message) { showToast(message); }

  function taskRow(task) {
    const assignee = employee(task.assigneeId);
    const due = new Date(`${task.due}T12:00:00`);
    return `<tr><td><b>${escapeHtml(task.title)}</b><br><small style="color:#829089">Автор: ${escapeHtml(employee(task.authorId).shortName)}</small></td><td><div class="person-cell"><span class="person-avatar">${escapeHtml(initialLetters(assignee.name))}</span><div><b>${escapeHtml(assignee.shortName)}</b><small>${escapeHtml(assignee.position)}</small></div></div></td><td>${formatDate(due)}</td><td><span class="status ${taskStatusClass(task.status)}">${escapeHtml(task.status)}</span></td><td><button class="btn btn-sm" onclick="Demo.toggleTask(${Number(task.id)})">${task.status === 'Выполнена' ? 'Вернуть' : 'Выполнить'}</button></td></tr>`;
  }

  function actionTask(task) {
    const assignee = employee(task.assigneeId);
    return `<div class="action-item"><span class="item-icon">✓</span><div class="item-copy"><b>${escapeHtml(task.title)}</b><small>${escapeHtml(assignee.shortName)} · срок ${formatDate(new Date(`${task.due}T12:00:00`))}</small></div><span class="status ${taskStatusClass(task.status)}">${escapeHtml(task.status)}</span></div>`;
  }

  function metric(label, value, note, spanClass) {
    return `<div class="card metric-card ${spanClass}"><small>${escapeHtml(label)}</small><strong>${escapeHtml(String(value))}</strong><span>${escapeHtml(note)}</span></div>`;
  }

  function messageBubble(message) {
    const me = Number(message.from) === CURRENT_USER_ID;
    const created = message.createdAt ? new Date(message.createdAt) : new Date(Date.now() + (message.offsetMinutes || 0) * 60000);
    return `<div class="bubble ${me ? 'me' : ''}">${escapeHtml(message.text)}<small>${me ? 'Иванов И.И.' : escapeHtml(employee(message.from).shortName)} · ${created.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}</small></div>`;
  }

  function lastMessage(chatId) {
    const list = state.messages[chatId] || [];
    return list.length ? list[list.length - 1].text : 'Нет сообщений';
  }

  function freshState() {
    const messages = {};
    Object.keys(baseMessages).forEach(key => {
      messages[key] = baseMessages[key].map(m => ({ ...m }));
    });
    return {
      generatedAt: Date.now(),
      dateKey,
      tasks: baseTasks.map(t => ({ ...t })),
      dutyJoined: [],
      dismissedAnnouncements: [],
      deferred: baseDeferred.map(r => ({ ...r, desired: toISO(r.desired) })),
      messages
    };
  }

  function loadState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return freshState();
      const parsed = JSON.parse(raw);
      if (parsed.dateKey !== dateKey || Date.now() - Number(parsed.generatedAt || 0) > RESET_MS) return freshState();
      return parsed;
    } catch (_) {
      return freshState();
    }
  }

  function saveState() {
    state.generatedAt = state.generatedAt || Date.now();
    state.dateKey = dateKey;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }

  function makeTask(id, title, authorId, assigneeId, dueOffset, status) {
    return { id, title, authorId, assigneeId, due: toISO(addDays(today, dueOffset)), status, created: toISO(addDays(today, -3)) };
  }

  function absence(employeeId, type, startOffset, endOffset, comment) {
    return { employeeId, type, start: addDays(today, startOffset), end: addDays(today, endOffset), comment };
  }

  function buildDuties() {
    const firstSaturday = nextWeekday(today, 6);
    return [
      { id: 1, date: firstSaturday, type: 'Дежурство терапевтического профиля', scope: 'Поликлиническое подразделение №1', participants: [2, 6, 10], open: true },
      { id: 2, date: addDays(firstSaturday, 7), type: 'Общее дежурство выходного дня', scope: 'Учреждение', participants: [16, 23, 32, 37], open: true },
      { id: 3, date: addDays(firstSaturday, 14), type: 'Дежурство терапевтического профиля', scope: 'Поликлиническое подразделение №1', participants: [3, 7, 12], open: true }
    ];
  }

  function employee(id) { return employees.find(e => e.id === Number(id)) || employees[0]; }

  function taskStatusClass(status) {
    if (status === 'Выполнена') return 'status-green';
    if (status === 'Просрочена') return 'status-red';
    if (status === 'В работе') return 'status-blue';
    return 'status-amber';
  }

  function reportStatusClass(status) {
    if (status === 'Черновик') return 'status-gray';
    if (status === 'Ожидает заполнения') return 'status-amber';
    return 'status-blue';
  }

  function deferredStatusClass(status) {
    if (status === 'Записан') return 'status-green';
    if (status === 'Предложен слот') return 'status-blue';
    return 'status-amber';
  }

  function absenceStatusClass(type) {
    if (type === 'Больничный') return 'status-red';
    if (type === 'Отпуск') return 'status-green';
    return 'status-blue';
  }

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add('show');
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(() => toast.classList.remove('show'), 2400);
  }

  function startOfDay(date) { return new Date(date.getFullYear(), date.getMonth(), date.getDate(), 12, 0, 0, 0); }
  function addDays(date, days) { const d = new Date(date); d.setDate(d.getDate() + days); return d; }
  function nextWeekday(date, weekdayNumber) {
    const d = new Date(date);
    let delta = (weekdayNumber - d.getDay() + 7) % 7;
    if (delta === 0) delta = 7;
    return addDays(d, delta);
  }
  function toISO(date) {
    const d = new Date(date);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }
  function formatDate(date) { return new Date(date).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' }); }
  function formatShort(date) { return new Date(date).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' }); }
  function formatLong(date) { return new Date(date).toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' }); }
  function formatRange(start, end) { return `${formatShort(start)} — ${formatDate(end)}`; }
  function weekday(date) { return new Date(date).toLocaleDateString('ru-RU', { weekday: 'long' }); }
  function monthName(date) { return new Date(date).toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' }); }
  function relativeDays(days) { if (days === 0) return 'сегодня'; if (days === 1) return 'завтра'; return `через ${days} дн.`; }

  function initials(fullName) {
    const parts = fullName.trim().split(/\s+/);
    return `${parts[0]} ${parts.slice(1).map(p => `${p[0]}.`).join('')}`;
  }
  function initialLetters(fullName) { return fullName.trim().split(/\s+/).slice(0, 2).map(p => p[0]).join('').toUpperCase(); }

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }
  function escapeAttr(value) { return escapeHtml(value); }
  function escapeJs(value) { return String(value ?? '').replaceAll('\\', '\\\\').replaceAll("'", "\\'").replaceAll('\n', ' '); }

  window.Demo = {
    go: navigate,
    openTaskDialog,
    toggleTask,
    toggleDuty,
    dismissAnnouncement,
    addDeferred,
    advanceDeferred,
    openChat,
    sendMessage,
    resetSandbox,
    generateDocument,
    fakeOpen
  };
})();
